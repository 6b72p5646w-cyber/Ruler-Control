#!/usr/bin/env python3
"""Render exact authored layouts as SVG; no generated art or external assets."""
import html
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=json.loads((ROOT/'content/maps.json').read_text())
OUT=ROOT/'docs/maps'
OUT.mkdir(parents=True,exist_ok=True)


def text(x,y,value,size=16,color='#dfe9ed',weight=400,anchor='start'):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}" text-anchor="{anchor}">{html.escape(str(value))}</text>'


def header(w,h):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
            '<style>text{font-family:"Noto Sans CJK SC","Microsoft YaHei",sans-serif}</style>',f'<rect width="{w}" height="{h}" fill="#101b25"/>']


def scene_svg(scene,ox,oy,s):
    out=[]
    def box(r,fill,stroke='none',dash=None):
        x,y,w,h=r
        return f'<rect x="{ox+x*s}" y="{oy+y*s}" width="{w*s}" height="{h*s}" fill="{fill}" stroke="{stroke}"'+(f' stroke-dasharray="{dash}"' if dash else '')+'/>'
    for r in scene['walk_surfaces']:out.append(box(r['rect'],'#20323c'))
    for z in scene['zones']:out.append(box(z['rect'],z['color']))
    allr=[r['rect'] for r in scene['walk_surfaces']]
    lo_x=min(r[0] for r in allr);hi_x=max(r[0]+r[2] for r in allr)
    lo_y=min(r[1] for r in allr);hi_y=max(r[1]+r[3] for r in allr)
    for x in range(lo_x,hi_x+1):out.append(f'<path d="M{ox+x*s},{oy+lo_y*s}V{oy+hi_y*s}" stroke="#5d7280" opacity=".17"/>')
    for y in range(lo_y,hi_y+1):out.append(f'<path d="M{ox+lo_x*s},{oy+y*s}H{ox+hi_x*s}" stroke="#5d7280" opacity=".17"/>')
    for r in scene['fixtures']:out.append(box(r['rect'],'#70818a','#b5c1c5'))
    for r in scene['walls']:out.append(box(r['rect'],'#080f16'))
    for r in scene['doors']:out.append(box(r['rect'],'#3b8877'))
    for r in scene['fixtures']:
        x,y,w,h=r['rect']
        if w>=2:out.append(text(ox+(x+w/2)*s,oy+(y+h/2)*s+4,r['name'],11,'#0c1921',600,'middle'))
    for a in scene['anchors']:
        x,y=a['position'];out.append(f'<circle cx="{ox+x*s}" cy="{oy+y*s}" r="2.7" fill="#81e3b3"/>')
    return out


def render_store():
    scene=DATA['scenes'][0];s=20;ox=42;oy=280
    out=header(1180,1150)
    out+=[text(42,48,'午夜便利店 · 地图布局 V0.4',30,weight=700),text(42,78,'连续俯瞰 / 店内 30×30 格 / 手机世界视野 12×15 格 / 面积比 5.0 屏',16,color='#a7bcc9')]
    out+=scene_svg(scene,ox,oy,s)
    # Zone captions are outside the congested fixture rows.
    for z in scene['zones']:
        x,y,w,h=z['rect'];out.append(text(ox+(x+w/2)*s,oy+(y+.8)*s,z['name'],13,'#d9edf5',600,'middle'))
    out.append(text(ox+10*s,oy+33*s,'店前空地',16,'#cce0e7',600,'middle'))
    out.append(text(ox+25*s,oy-7.5*s,'后门垃圾区',14,'#cce0e7',600,'middle'))
    out.append(text(ox+32*s,oy+18*s,'侧巷',13,'#cce0e7',600,'middle'))
    # One camera-sized world rectangle. It is a size reference, not a separate room.
    out.append(f'<rect x="{ox+7*s}" y="{oy+11*s}" width="{12*s}" height="{15*s}" fill="none" stroke="#ca98ff" stroke-width="3" stroke-dasharray="9 6"/>')
    lure=scene['lure_route']['bait_points']
    out.append('<polyline points="'+' '.join(f'{ox+x*s},{oy+y*s}' for x,y in lure)+'" fill="none" stroke="#efc464" stroke-width="3" stroke-dasharray="6 4"/>')
    for i,(x,y) in enumerate(lure,1):
        out.append(f'<circle cx="{ox+x*s}" cy="{oy+y*s}" r="8" fill="#efc464"/>')
        out.append(text(ox+x*s,oy+y*s+4,i,11,'#1b2730',700,'middle'))
    roles={a['role']:a for a in scene['anchors']}
    pins=[('A','cashier','收银 / 顾客保持距离'),('B','metal_shelf','回形针架 / 手动投放起点'),('C','warehouse_meat','任务生肉 / 独立任务携带槽'),('D','freezer_main','有效冰柜 / 入柜并关门'),('E','receiving','验收与称重'),('F','monitor_terminal','五路快照 / 不拍休息区'),('G','power_panel','三个固定供电回路'),('H','dumpster','垃圾投放 / 危险来自后院'),('I','forecourt_handoff','巨型顾客与百鬼交接'),('J','verification_desk','同事与店长核验')]
    for label,role,name in pins:
        x,y=roles[role]['position']
        out.append(f'<circle cx="{ox+x*s}" cy="{oy+y*s}" r="10" fill="#b1e8e1" stroke="#18313d" stroke-width="2"/>')
        out.append(text(ox+x*s,oy+y*s+4,label,12,'#12323b',700,'middle'))
    rx=770
    out.append(text(rx,140,'五个功能区，按面积合计五屏',20,weight=700))
    zone_desc=['前场收银  30×10 · 300格','商品货架  18×10 · 180格','熟食冷链  12×10 · 120格','库房验收  16×10 · 160格','员工设备  14×10 · 140格']
    for i,v in enumerate(zone_desc):out.append(text(rx,178+i*30,v,17))
    out.append(text(rx,350,'关键操作位置',20,weight=700))
    for i,(label,role,name) in enumerate(pins):out.append(text(rx,388+i*29,f'{label}  {name}',15))
    out.append(text(rx,712,'走位与公平性',20,weight=700))
    for i,v in enumerate(['主过道至少3格；后场有两条通路','前门—东巷—后门组成店外备用环路','前场保留4格顾客/收银间隔','金色虚线是4个手撒诱饵的教学路线','紫色框只表示视野大小，会跟随玩家','绿色点是可达操作格；黑色是实体墙','门外区域不计入店内五屏面积']):out.append(text(rx,750+i*28,v,15,color='#a7bcc9'))
    out.append(text(42,1094,'说明：这是坐标与路线设计图。地图美术、移动碰撞、触屏手感和怪物追逐尚待客户端实现与实测。',16,color='#a7bcc9'))
    out.append(text(42,1125,'尺寸与位置为本轮方案提案；F12 回形针诱离、F13 生肉入柜的用户确定条件保持不变。',15,color='#a7bcc9'))
    out.append('</svg>')
    (OUT/'store_layout.svg').write_text('\n'.join(out))


def render_day():
    out=header(1160,820)
    out+=[text(40,48,'白天地图 · 恢复、准备与知识成长',30,weight=700),text(40,80,'三个 12×15 格的单屏场景，通过街区行程图连接；无需开发一座可漫游城市。',16,color='#a7bcc9')]
    descriptions=[['床：睡眠和精力恢复','厨房：基础餐食和饱腹','书桌：怪物笔记与规则预演','柜 / 宠物角：装备与照料'],['基础货架：确定性补给','装备架：六槽配置与比较','奖券机：临时道具与保底','柜台：维修和宠物契约'],['资料架：按线索查母题','导师：驱魔方法与练习','档案柜：不同版本对照','阅读桌：整理观察记录']]
    for i,scene in enumerate(DATA['scenes'][1:]):
        ox=40+i*380;oy=150;s=24
        out.append(text(ox,125,scene['name'],22,weight=700))
        out+=scene_svg(scene,ox,oy,s)
        for j,line in enumerate(descriptions[i]):out.append(text(ox,552+j*30,line,16))
    out.append(text(40,720,'行动槽：08–20 共6个整2小时槽；20–22基础准备，22–24通勤与核验。地图浏览不再重复扣时。',16,color='#a7bcc9'))
    out.append(text(40,753,'店铺夜班时不能传送回家。家中基础恢复有保障；白天异常主要改变服务、情报和资源选择。',16,color='#a7bcc9'))
    out.append(text(40,786,'绿色点：实际操作位。基础过道和所有服务位已作静态可达检查；并非可玩的移动客户端。',15,color='#a7bcc9'))
    out.append('</svg>')
    (OUT/'daytime_layouts.svg').write_text('\n'.join(out))


def render_phone():
    out=header(900,880)
    out+=[text(36,45,'手机视野与操作尺度',28,weight=700),text(36,73,'360×720 逻辑界面示意；五屏指世界面积，不包含HUD。',16,color='#a7bcc9')]
    x,y=36,110
    out.append(f'<rect x="{x-8}" y="{y-8}" width="376" height="736" rx="26" fill="#070d14" stroke="#71828d"/>')
    out.append(f'<rect x="{x}" y="{y}" width="360" height="720" rx="18" fill="#172733"/>')
    out.append(text(x+16,y+27,'02:24   冷链整理',18,weight=700))
    out.append(text(x+16,y+54,'精力 72   SAN 60   饱腹 58   体力 81',13,color='#a6dbca'))
    out.append(f'<defs><clipPath id="phoneWorld"><rect x="{x}" y="{y+72}" width="360" height="450"/></clipPath></defs>')
    out.append('<g clip-path="url(#phoneWorld)">')
    out+=scene_svg(DATA['scenes'][0],x-7*30,y+72-11*30,30)
    px,py=x+6.5*30,y+72+8.5*30
    out.append(f'<path d="M{px},{py-17}L{px-10},{py+10}L{px+10},{py+10}Z" fill="#f4d37e" stroke="#fff1c5" stroke-width="2"/>')
    out.append(f'<circle cx="{px}" cy="{py}" r="126" fill="none" stroke="#b2c2dc" stroke-dasharray="6 5" opacity=".5"/>')
    out.append('</g>')
    out.append(f'<rect x="{x+10}" y="{y+478}" width="340" height="34" rx="7" fill="#17222f"/>')
    out.append(text(x+22,y+501,'↗ 后门异常：有脚步接近',15,color='#f4c47c'))
    out.append(text(x+16,y+548,'手持：空   ｜   任务物：回形针 ×6',14))
    out.append(f'<circle cx="{x+78}" cy="{y+625}" r="48" fill="#314852" stroke="#6d8d9e"/>')
    out.append(f'<circle cx="{x+78}" cy="{y+625}" r="20" fill="#8bb8be"/>')
    for bx,by,label in [(x+190,y+610,'锁朝向'),(x+278,y+610,'交互'),(x+278,y+676,'快捷物')]:
        out.append(f'<rect x="{bx-36}" y="{by-23}" width="72" height="46" rx="12" fill="#375765"/>')
        out.append(text(bx,by+5,label,14,anchor='middle'))
    out.append(text(450,156,'世界视野：12×15 格',23,weight=700))
    lines=[('面积','店内900格 ÷ 单屏180格 = 5屏'),('移动','左手摇杆；角色约0.6格碰撞直径'),('操作','右侧基础动作、快捷物和锁朝向'),('尺度','地图取放 / 工位安排 / 安全特写'),('低SAN','判定区变小、周边黑视；输入不乱跳'),('保留','HUD、退出、方向提示保持可读'),('镜头','跟随平移，无强制旋转或频繁切房'),('触控','基础按钮46逻辑像素高，不随SAN缩小')]
    for i,(a,b) in enumerate(lines):
        yy=211+i*67
        out.append(text(450,yy,a,14,'#88b8c8',700));out.append(text(450,yy+25,b,16))
    out.append(text(450,800,'这是布局示意，数值并非游戏运行截图。',15,color='#a7bcc9'))
    out.append('</svg>')
    (OUT/'phone_view.svg').write_text('\n'.join(out))


if __name__=='__main__':
    render_store();render_day();render_phone()
    print('Rendered three map SVG layouts')
