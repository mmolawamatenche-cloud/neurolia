import ast, sys
sys.stdout.reconfigure(encoding='utf-8')
files = ['lia4.py','engine.py','lia_core.py','voice.py','commands.py','static_gestures.py']
for f in files:
    try:
        ast.parse(open(f, encoding='utf-8').read())
        print('OK:', f)
    except SyntaxError as e:
        print('SYNTAX ERROR:', f, e)
