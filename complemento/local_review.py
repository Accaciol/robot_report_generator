"""Fila local de demonstração. Nenhuma criação real no Azure."""
from __future__ import annotations

import copy
import hmac
import json
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit


def validate_destination(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ValueError('Configuração inválida.')
    keys = ('board_url', 'work_item_type', 'initial_state', 'desired_column',
            'area_path', 'iteration_path', 'assigned_to', 'priority', 'tags')
    config = {}
    for key in keys:
        text = value.get(key, '')
        if not isinstance(text, str) or len(text) > (2000 if key == 'board_url' else 500):
            raise ValueError('Campo de configuração inválido.')
        config[key] = text.strip()
    url = urlsplit(config['board_url'])
    parts = [unquote(part) for part in url.path.split('/') if part]
    if (url.scheme != 'https' or url.netloc != 'dev.azure.com'
            or url.username or url.password or url.query or url.fragment
            or len(parts) < 3 or parts[2] != '_boards'
            or any(part in ('.', '..') or '/' in part or '\\' in part for part in parts)):
        raise ValueError('Informe um link de board https://dev.azure.com/organização/projeto/_boards/...')
    config.update(organization=parts[0], project=parts[1])
    config['work_item_type'] = config['work_item_type'] or 'Bug'
    return config


class Review:
    def __init__(self, matrix: dict, path: Path):
        self.matrix = copy.deepcopy(matrix)
        self.path = path
        self.lock = threading.RLock()
        self.state = {'report_id': matrix['report_id'], 'mode': 'simulation',
                      'status': 'idle', 'config': {}, 'results': [], 'active': None}
        self._committed = copy.deepcopy(self.state)
        if path.exists():
            try:
                saved = json.loads(path.read_text(encoding='utf-8'))
                if (saved['report_id'] != matrix['report_id'] or saved['mode'] != 'simulation'
                        or not isinstance(saved['results'], list)
                        or saved['status'] not in ('idle', 'ready', 'opening', 'awaiting_decision',
                                                   'paused', 'completed')):
                    raise ValueError('Estado incompatível.')
                ids = [item['candidate_id'] for item in saved['results']]
                expected = [item['candidate_id'] for item in matrix['candidates'][:len(ids)]]
                if ids != expected or len(ids) > len(matrix['candidates']):
                    raise ValueError('Decisões incompatíveis com o relatório.')
                for index, result in enumerate(saved['results']):
                    expected_code = f'SIM-{index + 1:04d}' if result['status'] == 'saved' else None
                    if (result['status'] not in ('saved', 'discarded')
                            or result['simulation_id'] != expected_code
                            or result['work_item_id'] is not None or result['work_item_url'] is not None
                            or not isinstance(result['reviewed_title'], str)
                            or not isinstance(result['reviewed_description'], str)
                            or result['attachments_status'] != 'not_uploaded'):
                        raise ValueError('Resultado local inválido.')
                if saved['status'] != 'idle':
                    validate_destination(saved['config'])
                    if (saved['status'] == 'completed') != (len(ids) == len(matrix['candidates'])):
                        raise ValueError('Estado de conclusão inconsistente.')
                elif ids:
                    raise ValueError('Execução não preparada contém decisões.')
                self.state = saved
                self._committed = copy.deepcopy(saved)
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError('Estado local inválido; preserve o arquivo para reconciliação.') from exc
            if self.state['status'] in ('opening', 'awaiting_decision'):
                self.state.update(status='paused', active=None)
                self._persist()

    def _persist(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.state, ensure_ascii=False), encoding='utf-8')
            temporary.replace(self.path)
        except OSError:
            self.state = copy.deepcopy(self._committed)
            raise
        self._committed = copy.deepcopy(self.state)

    def snapshot(self) -> dict:
        with self.lock:
            result = copy.deepcopy(self.state)
            # The attempt proof belongs only to the current form, never to the report/export.
            result['active'] = (self.state['active'] or {}).get('candidate_id')
            result['total'] = len(self.matrix['candidates'])
            return result

    def prepare(self, config: dict) -> None:
        with self.lock:
            if self.state['status'] != 'idle':
                raise ValueError('Esta execução já foi preparada.')
            self.state.update(config=validate_destination(config),
                              status='ready' if self.matrix['candidates'] else 'completed')
            self._persist()

    def open_next(self) -> tuple[dict, str]:
        with self.lock:
            if self.state['status'] not in ('ready', 'paused'):
                raise ValueError('Não há candidato disponível para abrir.')
            candidate = self.matrix['candidates'][len(self.state['results'])]
            attempt = secrets.token_urlsafe(24)
            self.state.update(status='opening', active={'candidate_id': candidate['candidate_id'],
                                                        'attempt': attempt})
            self._persist()
            return copy.deepcopy(candidate), attempt

    def form(self) -> tuple[dict, str]:
        with self.lock:
            if self.state['status'] not in ('opening', 'awaiting_decision'):
                raise ValueError('Nenhum formulário ativo.')
            return (copy.deepcopy(self.matrix['candidates'][len(self.state['results'])]),
                    self.state['active']['attempt'])

    def opened(self) -> None:
        with self.lock:
            if self.state['status'] == 'opening':
                self.state['status'] = 'awaiting_decision'
                self._persist()

    def pause(self) -> None:
        with self.lock:
            if self.state['status'] in ('opening', 'awaiting_decision'):
                self.state.update(status='paused', active=None)
                self._persist()

    def decide(self, candidate_id: str, attempt: str, status: str, title: str, description: str) -> None:
        with self.lock:
            active = self.state['active'] or {}
            if (self.state['status'] not in ('opening', 'awaiting_decision')
                    or candidate_id != active.get('candidate_id') or not isinstance(attempt, str)
                    or not hmac.compare_digest(attempt.encode(), active.get('attempt', '').encode())):
                raise ValueError('Decisão vencida ou sem correspondência com o formulário ativo.')
            if (status not in ('saved', 'discarded') or not isinstance(title, str)
                    or not isinstance(description, str) or len(title) > 500
                    or len(description) > 20000 or (status == 'saved' and not title.strip())):
                raise ValueError('Decisão ou conteúdo inválido.')
            result = {'candidate_id': candidate_id, 'status': status, 'reviewed_title': title,
                      'reviewed_description': description, 'work_item_id': None, 'work_item_url': None,
                      'simulation_id': f'SIM-{len(self.state["results"]) + 1:04d}' if status == 'saved' else None,
                      'attachments_status': 'not_uploaded',
                      'confirmed_at': datetime.now(timezone.utc).isoformat()}
            self.state['results'].append(result)
            self.state.update(active=None, status='completed' if len(self.state['results']) ==
                              len(self.matrix['candidates']) else 'ready')
            self._persist()
