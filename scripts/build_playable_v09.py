#!/usr/bin/env python3
"""Bundle the repository's dependency-free ES modules and exact data into one HTML.

This small bundler intentionally accepts only the import/export declarations used
by this slice. Unknown syntax fails; it never rewrites game rules or substitutes
an alternate simulation for a browser preview.
"""
from pathlib import Path
import re,json,hashlib

ROOT=Path(__file__).resolve().parents[1]
ENTRY=ROOT/'prototype/playable_v09.mjs'
DATA={'maps':'maps','blueprints':'encounter_blueprints','mechanics':'map_mechanics_v05',
      'interactions':'interactions','balance':'balance','condition':'condition_lifecycle_v06',
      'items':'items','qte':'qte','integration':'integration_v09'}
imports=re.compile(r"^import\s+(\*\s+as\s+\w+|\{[^}]+\})\s+from\s+['\"]([^'\"]+)['\"];?",re.M)
modules={};blocks=[];hashes={}
def read(path):
 raw=path.read_bytes();hashes[str(path.relative_to(ROOT))]=hashlib.sha256(raw).hexdigest();return raw.decode('utf-8')
def bundle(path):
 path=path.resolve()
 if path in modules:return modules[path]
 if not path.is_relative_to(ROOT/'prototype') or path.suffix!='.mjs':raise ValueError('Unexpected dependency '+str(path))
 text=read(path);bindings=[]
 for m in imports.finditer(text):
  clause,target=m.groups()
  if not target.startswith('./'):raise ValueError('Only local module dependencies are allowed')
  name=bundle(path.parent/target)
  if clause.startswith('*'):bindings.append('const '+clause.split()[-1]+' = '+name+';')
  else:bindings.append('const '+re.sub(r'\s+as\s+',': ',clause)+' = '+name+';')
 text=imports.sub('',text)
 exports=re.findall(r'^export\s+(?:async\s+)?(?:function|class|const|let)\s+(\w+)',text,re.M)
 text=re.sub(r'^export\s+(?=(?:async\s+)?(?:function|class|const|let)\b)','',text,flags=re.M)
 if re.search(r'^\s*(?:import|export)\s',text,re.M):raise ValueError('Unsupported module declaration in '+str(path))
 name='__midnight_module_'+str(len(modules));modules[path]=name
 blocks.append('const '+name+' = (() => {\n'+ '\n'.join(bindings)+'\n'+text+'\nreturn {'+', '.join(exports)+'};\n})();')
 return name
bundle(ENTRY)
payload={key:json.loads(read(ROOT/'content'/f'{stem}.json')) for key,stem in DATA.items()}
css=read(ROOT/'prototype/playable_v09.css');template=read(ROOT/'prototype/playable_v09.template.html')
data='window.MIDNIGHT_DATA = '+json.dumps(payload,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')+';'
js='"use strict";\n'+ '\n'.join(blocks)
if '</script' in js.lower():raise ValueError('Literal script terminator in module source')
html=template.replace('/* BUILD_CSS */',css).replace('/* BUILD_DATA */',data).replace('/* BUILD_JS */',js)
if re.search(r'<(?:script|link)[^>]+(?:src|href)=',html,re.I):raise ValueError('Preview has an external resource dependency')
output=ROOT/'prototype/playable_v09.html';output.write_text(html)
report={'status':'PASS','standalone_html':'prototype/playable_v09.html','bytes':output.stat().st_size,
 'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'module_count':len(modules),
 'source_sha256':hashes,'scope':'Reproducible single-file build; functionality and rendering are checked separately.'}
(ROOT/'docs/playable_build_v09.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':'PASS','output':str(output),'bytes':report['bytes'],'modules':len(modules)}))
