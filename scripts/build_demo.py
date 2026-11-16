"""Executa casos Robot fictícios e gera uma demonstração portátil."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from complemento.generate_report import generate


def main() -> None:
    from PIL import Image, ImageDraw
    results = ROOT / 'demo' / 'results'
    results.mkdir(parents=True, exist_ok=True)
    image = Image.new('RGB', (640, 200), '#f6f9f7')
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 640, 42), fill='#18352f')
    draw.text((20, 15), 'SISTEMA FICTICIO | EVIDENCIA DE DEMONSTRACAO', fill='white')
    draw.text((20, 80), 'Falha de exemplo: nao foi possivel concluir a operacao.', fill='#18352f')
    draw.text((20, 120), 'Sem dados reais. Nenhum sistema corporativo foi acessado.', fill='#18352f')
    image.save(results / 'evidencia.png')
    command = [sys.executable, '-m', 'robot', '--outputdir', str(results), '--log', 'NONE',
               '--report', 'NONE', str(ROOT / 'demo' / 'casos_sinteticos.robot')]
    run = subprocess.run(command, check=False)
    if run.returncode != 3:
        raise SystemExit(f'Esperadas 3 falhas sintéticas; Robot retornou {run.returncode}.')
    matrix = generate(results, ROOT / 'demo' / 'relatorio-demo.html')
    print(f"Demonstração pronta: {len(matrix['candidates'])} formulários simulados.")


if __name__ == '__main__':
    main()
