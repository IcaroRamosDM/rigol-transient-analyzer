"""Static translation coverage and JavaScript module checks."""
from html.parser import HTMLParser
from pathlib import Path
import json
import ast
import os
import re
import shutil
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]
class Localization(unittest.TestCase):
    def test_visible_static_text_and_accessibility_have_english_translations(self):
        source=(ROOT/"interface/static/modules/i18n.js").read_text(encoding="utf-8")
        catalog=json.loads(source.split("export const english=",1)[1].split(";\nconst fragments=",1)[0])
        missing=set()
        class Text(HTMLParser):
            def handle_data(self,data):
                key=re.sub(r"\s+"," ",data).strip()
                if len(key)>3 and any(c.isalpha() for c in key) and key not in catalog and not key.startswith(("Rigol","RIGOL")) and key not in {"Transient Analyzer","Português","English","Idioma / Language"}:
                    missing.add(key)
            def handle_starttag(self,tag,attrs):
                for key,value in attrs:
                    if key in {"alt","aria-label","title","placeholder"} and value not in catalog and value!="Idioma / Language" and not value.startswith("169."):
                        missing.add(value)
        Text().feed((ROOT/"interface/static/index.html").read_text(encoding="utf-8"))
        self.assertEqual(missing,set())
        self.assertEqual(catalog["Sinal sintetico deterministico; nenhuma medicao fisica"],"Deterministic synthetic signal; no physical measurement")

    def test_api_validation_messages_have_english_presentations(self):
        source=(ROOT/"interface/static/modules/i18n.js").read_text(encoding="utf-8")
        catalog=json.loads(source.split("export const english=",1)[1].split(";\nconst fragments=",1)[0])
        missing=set()
        for path in (ROOT/"interface/rta").glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=="Problem" and node.args:
                    value=node.args[0]
                    while isinstance(value,ast.BinOp):value=value.left
                    if isinstance(value,ast.Constant) and isinstance(value.value,str) and value.value.strip() not in catalog:
                        missing.add(value.value.strip())
        self.assertEqual(missing,set())

    def test_javascript_syntax_and_dictionary_do_not_translate_protocol_tokens(self):
        node=os.environ.get("NODE") or shutil.which("node")
        if not node:self.skipTest("Node.js is required for JavaScript syntax checks")
        for path in (ROOT/"interface/static").rglob("*.js"):
            result=subprocess.run([node,"--input-type=module","--check"],input=path.read_bytes(),capture_output=True,timeout=15)
            self.assertEqual(result.returncode,0,path.name+": "+result.stderr.decode("utf-8",errors="replace"))
        source=(ROOT/"interface/static/modules/i18n.js").read_text(encoding="utf-8")
        script="globalThis.localStorage={getItem:()=> 'en'};\nconst m=await import('data:text/javascript;base64,"+__import__("base64").b64encode(source.encode()).decode()+"');\n"
        script+="if(m.t('SIMULACAO')!=='SIMULACAO'||m.t('subida')!=='rising'||m.locale!=='en-US')throw Error('Localization altered protocol values');"
        result=subprocess.run([node,"--input-type=module"],input=script.encode(),capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr.decode("utf-8",errors="replace"))
