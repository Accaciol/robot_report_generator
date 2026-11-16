"""Gera dois pacotes de instalação com a mesma fonte Manifest V3."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'extension' / 'src'


def build() -> dict:
    hashes = {}
    for browser in ('edge', 'chrome'):
        destination = ROOT / 'extensions' / browser
        destination.mkdir(parents=True, exist_ok=True)
        for source in SOURCE.iterdir():
            if source.is_file():
                shutil.copyfile(source, destination / source.name)
        manifest = json.loads((SOURCE / 'manifest.json').read_text(encoding='utf-8'))
        manifest['name'] = f'Ruzy para {browser.title()} · DEMONSTRAÇÃO'
        (destination / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        (destination / 'INSTALAR.md').write_text(
            f'# Ruzy para {browser.title()} — demonstração\n\n'
            f'Abra {"edge" if browser == "edge" else "chrome"}://extensions, ative Modo do desenvolvedor '
            'e carregue esta pasta sem compactação. Habilite acesso a URLs de arquivos nos detalhes da extensão.\n\n'
            'Depois abra demo/relatorio-demo.html no mesmo navegador. Veja INSTALAR-RUZY.md na raiz do projeto.\n'
            'Esta versão não acessa o Azure; todos os formulários e códigos SIM são fictícios.\n', encoding='utf-8')
        archive = ROOT / 'dist' / f'ruzy-{browser}-demo.zip'
        archive.parent.mkdir(exist_ok=True)
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zipped:
            for file in sorted(destination.iterdir()):
                if file.is_file():
                    zipped.write(file, file.name)
        hashes[browser] = hashlib.sha256(archive.read_bytes()).hexdigest()
    (ROOT / 'dist' / 'SHA256SUMS.json').write_text(json.dumps(hashes, indent=2)+'\n', encoding='utf-8')
    kit = ROOT / 'dist' / 'ruzy-demonstracao.zip'
    with zipfile.ZipFile(kit, 'w', zipfile.ZIP_DEFLATED) as zipped:
        for directory in ('extensions', 'demo', 'complemento', 'scripts', 'tests', 'core', 'templates'):
            for file in sorted((ROOT / directory).rglob('*')):
                if not file.is_file() or '__pycache__' in file.parts or 'results' in file.relative_to(ROOT).parts:
                    continue
                zipped.write(file, file.relative_to(ROOT).as_posix())
        for filename in ('README.md', 'README-RUZY-ALPHA.md', 'INSTALAR-RUZY.md', 'requirements-ruzy-dev.txt', 'models.py', 'main.py', 'gui.py', 'pyproject.toml', 'requirements.txt'):
            zipped.write(ROOT / filename, filename)
    hashes['demonstracao'] = hashlib.sha256(kit.read_bytes()).hexdigest()
    (ROOT / 'dist' / 'SHA256SUMS.json').write_text(json.dumps(hashes, indent=2)+'\n', encoding='utf-8')
    return hashes


if __name__ == '__main__':
    print(json.dumps(build(), indent=2))
