#!/usr/bin/env python3
"""Render exact V0.5 store mechanics as two equal-scale SVG panels."""
import html
import json
from collections import defaultdict
from pathlib import Path

from validate_maps import cell, cells, graph, shortest
from validate_map_mechanics_v05 import validate

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/maps/store_mechanics_v05.svg'
S = 18
WIDTH, HEIGHT = 2200, 1180
ORIGINS = [(56, 324), (1140, 324)]
ZONE_COLORS = ['#e0f2fe', '#ecfccb', '#dbeafe', '#fef3c7', '#f3e8ff']
WET_COLORS = ['#0891b2', '#2563eb', '#0f766e', '#7c3aed', '#d97706']


def label(x, y, value, size=15, color='#1e293b', weight=400, anchor='start'):
    return (f'<text x="{x:g}" y="{y:g}" font-size="{size:g}" fill="{color}" '
            f'font-weight="{weight}" text-anchor="{anchor}">{html.escape(str(value))}</text>')


def rect(x, y, w, h, fill, stroke='none', width=1, dash=None, radius=0, opacity=1):
    return (f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{radius:g}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{width:g}" opacity="{opacity:g}"'
            + (f' stroke-dasharray="{dash}"' if dash else '') + '/>')


def world_rect(origin, r, fill, **kw):
    ox, oy = origin
    x, y, w, h = r
    return rect(ox+x*S, oy+y*S, w*S, h*S, fill, **kw)


def point(origin, p):
    return origin[0] + p[0]*S, origin[1] + p[1]*S


def line(a, b, color='#64748b', width=1.2, dash=None):
    return (f'<path d="M{a[0]:g},{a[1]:g} L{b[0]:g},{b[1]:g}" stroke="{color}" '
            f'stroke-width="{width:g}" fill="none"' + (f' stroke-dasharray="{dash}"' if dash else '') + '/>')


def pill(out, x, y, value, fill, font=12, stroke='#ffffff'):
    w = max(24, len(value)*font*.68 + 12)
    out.append(rect(x-w/2, y-11, w, 22, fill, stroke=stroke, width=1.5, radius=5))
    out.append(label(x, y+4, value, font, '#ffffff', 700, 'middle'))


def backdrop(out, scene, origin):
    ox, oy = origin
    for surface in scene['walk_surfaces']:
        out.append(world_rect(origin, surface['rect'], '#eef2f6', stroke='#a8b4c2'))
    for zone, color in zip(scene['zones'], ZONE_COLORS):
        out.append(world_rect(origin, zone['rect'], color))
    for surface in scene['walk_surfaces']:
        out.append(world_rect(origin, surface['rect'], f'url(#grid{ORIGINS.index(origin)})'))
    for fixture in scene['fixtures']:
        out.append(world_rect(origin, fixture['rect'], '#c6ced7', stroke='#8291a3', width=.8))
    for wall in scene['walls']:
        out.append(world_rect(origin, wall['rect'], '#243447'))
    for door in scene['doors']:
        out.append(world_rect(origin, door['rect'], '#86efac', stroke='#15803d', width=.7))
    for fixture in scene['fixtures']:
        x,y,w,h = fixture['rect']
        name = fixture['name'] if w >= 2 else fixture['id'][-2:]
        out.append(label(ox+(x+w/2)*S, oy+(y+h/2)*S+3.5, name, 10, '#334155', 500, 'middle'))
    out.append(world_rect(origin, scene['interior_rect'], 'none', stroke='#0f172a', width=2))
    out.append(label(ox+10*S, oy+36.8*S, '店前空地', 16, '#64748b', 600, 'middle'))
    out.append(label(ox+24.5*S, oy-7.35*S, '后院垃圾区', 14, '#64748b', 600, 'middle'))
    for i,ch in enumerate('东侧巷'):
        out.append(label(ox+32*S, oy+(16+i)*S, ch, 14, '#64748b', 600, 'middle'))
    # Axis labels outside all walk surfaces.
    for x in range(0,35,5):
        out.append(label(ox+x*S, oy+39.2*S, x, 12, '#64748b', anchor='middle'))
    for y in range(-5,39,5):
        out.append(label(ox-12, oy+(y+.2)*S, y, 12, '#64748b', anchor='end'))
    # This legend occupies the empty non-walkable area left of the rear yard.
    out.append(label(ox+S, oy-7.1*S, '店内五区 · 30×30 格', 14, '#334155', 700))
    for i,(z,color) in enumerate(zip(scene['zones'], ZONE_COLORS)):
        yy=oy-6.25*S+i*20
        out.append(rect(ox+S, yy-11, 12, 12, color, stroke='#94a3b8'))
        out.append(label(ox+S+20, yy, f'{z["id"]}  {z["name"]}', 13, '#475569'))


def bottleneck(out, origin):
    out.append(world_rect(origin,[25,3,2,1],'#ef4444',stroke='#b91c1c',width=2,opacity=.65))
    a=point(origin,[25.5,3.5]);b=point(origin,[23.5,5.2])
    out.append(line(a,b,'#b91c1c',1.5));pill(out,*b,'L1','#b91c1c')


def objects_panel(out, scene, data):
    origin=ORIGINS[0]
    backdrop(out,scene,origin)
    out.append(world_rect(origin,[7,11,12,15],'none',stroke='#a855f7',width=1.6,dash='7 5'))
    x,y=point(origin,[7,10.7]);out.append(label(x,y,'12×15 格：一屏尺度参考',12,'#9333ea',600))
    names=[obj['name'] for obj in data['objects']]
    offsets={
        '01':(-28,20),'02':(23,15),'03':(0,38),'04':(0,22),'05':(32,8),
        '06/07':(30,-19),'08':(0,-18),'09':(-23,22),'10':(0,18),'11':(0,-20),
        '12/13':(-31,-25),'14':(0,-17),'15':(-5,24),'16':(29,8),
        '17':(0,-20),'18':(0,23),'19':(-8,-16)}
    grouped=defaultdict(list)
    for i,obj in enumerate(data['objects'],1):
        grouped[tuple(obj['player_position'])].append(f'{i:02d}')
    for position,numbers in grouped.items():
        value='/'.join(numbers);a=point(origin,position);dx,dy=offsets.get(value,(0,-18));b=(a[0]+dx,a[1]+dy)
        out.append(line(a,b,'#0f766e',1.2))
        out.append(f'<circle cx="{a[0]:g}" cy="{a[1]:g}" r="3.3" fill="#064e3b" stroke="#ffffff" stroke-width="1"/>')
        pill(out,*b,value,'#0f766e',11)
    bottleneck(out,origin)
    lx=714
    out.append(label(lx,180,'物件编号 → 玩家操作位',21,weight=700))
    out.append(label(lx,206,'圆点是坐标；引线数字不占据地格。',14,'#64748b'))
    for i,(name,obj) in enumerate(zip(names,data['objects']),1):
        yy=242+(i-1)*26
        pill(out,lx+17,yy-4,f'{i:02d}','#0f766e',11)
        out.append(label(lx+41,yy,name,15))
    out.append(label(lx,765,'机制层边界',20,weight=700))
    for i,txt in enumerate([
        '台面物件与脚下操作位分别登记。',
        '帘、标牌、粉印不增加导航障碍。',
        '柜台不是全怪无敌区。',
        '快照只证明拍摄时刻和视域。',
        'F12 / F13 的确定解法保持。']):
        out.append(label(lx,796+i*27,txt,15,'#475569'))
    out.append(rect(lx,943,322,66,'#faf5ff',stroke='#d8b4fe',radius=8))
    out.append(label(lx+12,969,'900 格 ÷ 180 格 = 5 屏',17,'#7e22ce',700))
    out.append(label(lx+12,993,'前场、后院、东侧巷额外计算。',14,'#7e22ce'))


def wet_panel(out, scene, data, report):
    origin=ORIGINS[1]
    backdrop(out,scene,origin)
    grid=graph(scene)&cells(scene['interior_rect'])
    route=shortest(grid,(15,28),(27,1))
    route_points=[point(origin,[x+.5,y+.5]) for x,y in route]
    out.append('<polyline points="'+' '.join(f'{x:g},{y:g}' for x,y in route_points)+'" fill="none" stroke="#64748b" stroke-width="2" stroke-dasharray="4 4" opacity=".65"/>')
    wet_labels={'WET_FRONT':(-44,8),'WET_COLD':(-35,-25),'WET_REAR':(35,-18),'WET_AISLE':(-34,-20),'WET_CHAIR':(-16,29)}
    for i,(region,color) in enumerate(zip(data['wet_regions'],WET_COLORS),1):
        for x,y in region['wet_cells']:
            out.append(world_rect(origin,[x,y,1,1],color,stroke=color,width=1,opacity=.6))
        sx,sy=point(origin,[v+.5 for v in region['source_cell']])
        out.append(f'<circle cx="{sx:g}" cy="{sy:g}" r="4.5" fill="{color}" stroke="#ffffff" stroke-width="1.3"/>')
        cx,cy=point(origin,[v+.5 for v in region['cut_cell']])
        out.append(line((cx-5,cy-5),(cx+5,cy+5),'#ffffff',2.4));out.append(line((cx-5,cy+5),(cx+5,cy-5),'#ffffff',2.4))
        dx,dy=point(origin,region['dry_interact_position'])
        out.append(f'<path d="M{dx:g},{dy-6:g}L{dx+6:g},{dy:g}L{dx:g},{dy+6:g}L{dx-6:g},{dy:g}Z" fill="#ffffff" stroke="#14532d" stroke-width="2"/>')
        ox,oy=wet_labels[region['id']];b=(cx+ox,cy+oy)
        out.append(line((cx,cy),b,color,1.4));pill(out,*b,f'W{i}',color)
    grouped=defaultdict(list)
    for i,entry in enumerate(data['entry_profiles'],1):
        grouped[tuple(entry['positions'][0])].append(str(i))
    for position,nums in grouped.items():
        x,y=point(origin,position)
        out.append(f'<circle cx="{x:g}" cy="{y:g}" r="9" fill="#ffffff" stroke="#334155" stroke-width="2"/>')
        value='E'+'/'.join(nums)
        out.append(label(x+13,y+4,value,12,'#0f172a',700))
    bottleneck(out,origin)
    lx=1798
    out.append(label(lx,180,'湿区：水源—割点—干侧',21,weight=700))
    for i,(region,color) in enumerate(zip(data['wet_regions'],WET_COLORS),1):
        yy=225+(i-1)*67
        pill(out,lx+18,yy-5,f'W{i}',color)
        out.append(label(lx+44,yy,region['name'],16,weight=600))
        cut=','.join(map(str,region['cut_cell']));dry=','.join(map(str,region['dry_interact_position']))
        out.append(label(lx+44,yy+21,f'{len(region["wet_cells"])} 格；割点 ({cut})',13,'#475569'))
        out.append(label(lx+44,yy+41,f'干侧操作 ({dry})',13,'#475569'))
    out.append(label(lx,570,'实心点：水源   白 ×：割点',14,'#475569'))
    out.append(label(lx,593,'白菱形：干侧操作   圆圈：入口',14,'#475569'))
    out.append(label(lx,631,'入口档案（共点合并标记）',19,weight=700))
    entry_names=['正门公开来客','后门有限验收','货架预告后显现','物件附着：测试位','F12 原蓝图出生位','F13 后门接近肉箱']
    for i,name in enumerate(entry_names,1):
        out.append(label(lx,659+(i-1)*25,f'E{i}  {name}',15))
    out.append(rect(lx,818,338,193,'#fff1f2',stroke='#fda4af',radius=8))
    out.append(label(lx+12,848,'红框 L1：后场窄连接',19,'#991b1b',700))
    probe_by_id={p['id']:p for p in report['clearance_probes']}
    inner=probe_by_id['PROBE_PLAYER_INTERIOR']['path_tiles']
    outer=probe_by_id['PROBE_WIDE_EXTERNAL_ROUTE']['path_tiles']
    for i,(txt,col) in enumerate([
        (f'0.3 格半径：店内 {inner} 格可达。','#475569'),
        ('0.75 格半径：店内不可达。','#b91c1c'),
        (f'宽体外绕 {outer} 格，须双门可通。','#475569'),
        ('不启用体型成长；仍需碰撞实测。','#991b1b')]):
        out.append(label(lx+12,878+i*27,txt,14,col,600 if i in [1,3] else 400))


def main():
    base=json.loads((ROOT/'content/maps.json').read_text())
    data=json.loads((ROOT/'content/map_mechanics_v05.json').read_text())
    scene=next(s for s in base['scenes'] if s['id']==data['scene_id'])
    report=validate()
    if report['status']!='PASS':
        raise SystemExit(json.dumps(report['errors'],ensure_ascii=False))
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
         '<title>午夜便利店 V0.5 共享机制地图</title>',
         '<desc>同尺度双图：左图为19项操作位，右图为离散湿区、入口与窄路限制。由maps.json和map_mechanics_v05.json直接绘制。</desc>',
         '<style>text{font-family:"Noto Sans CJK SC","Microsoft YaHei",sans-serif}</style>',
         '<defs>'+''.join(f'<pattern id="grid{i}" x="{ox}" y="{oy}" width="18" height="18" viewBox="0 0 18 18" patternUnits="userSpaceOnUse"><path d="M18 0H0V18" fill="none" stroke="#94a3b8" stroke-width=".45" opacity=".4"/></pattern>' for i,(ox,oy) in enumerate(ORIGINS))+'</defs>',
         rect(0,0,WIDTH,HEIGHT,'#f1f5f9'),
         rect(32,106,1048,956,'#ffffff',stroke='#cbd5e1',radius=14),
         rect(1116,106,1052,956,'#ffffff',stroke='#cbd5e1',radius=14),
         label(40,48,'午夜便利店 · 共享机制地图 V0.5',34,weight=700),
         label(40,82,'精确坐标补件：先建立可操作的门、证据、交接与湿区，再由怪物改变这些物件的条件。',18,'#475569'),
         label(56,142,'A  物件与操作位',24,weight=700),
         label(1140,142,'B  湿区、入口与通路限制',24,weight=700)]
    objects_panel(out,scene,data)
    wet_panel(out,scene,data,report)
    out.append(label(40,1100,'两幅地图比例一致：1 格 = 18 px。墙、设备、五区与内外轮廓直接读取底图；所有新增点直接读取 V0.5 补件。',17,'#334155'))
    out.append(label(40,1129,f'静态校验 PASS（{report["checks"]} 项）。路径虚线仅表示基础角色的店内格心路线；并非全图三格宽，也不代表动态避让通过。',16,'#475569'))
    out.append(label(40,1157,'这是设计规格图，非游戏运行截图。移动碰撞、触屏、黑视可读性、动态怪物与微信实机仍待实现和验证。',16,'#64748b'))
    out.append('</svg>')
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text('\n'.join(out)+'\n')
    print(f'Rendered {OUT.relative_to(ROOT)} ({WIDTH}×{HEIGHT}) from authored geometry')


if __name__=='__main__':
    main()
