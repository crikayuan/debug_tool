# -*- coding: utf-8 -*-
"""双实例端到端联调：实例1 作 TCP Server，实例2 作 TCP Client，双向收发验证"""
import asyncio
import json
import os
import subprocess
import time
import urllib.request
import urllib.error

import psutil
import websockets

EXE = r'C:\Users\yuanj\调试助手\调试助手.exe'
CWD = os.path.dirname(EXE)
BASE1 = 'http://127.0.0.1:20001'
BASE2 = 'http://127.0.0.1:20002'
TCP_PORT = 6100


def http(base, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    if data:
        req.add_header('Content-Type', 'application/json')
    try:
        return json.loads(urllib.request.urlopen(req, timeout=5).read().decode())
    except urllib.error.HTTPError as e:
        return {'_error': e.code, '_detail': e.read().decode()[:200]}


def kill_all():
    for p in psutil.process_iter(['pid', 'exe']):
        try:
            if (p.info.get('exe') or '').endswith('调试助手.exe'):
                p.kill()
        except Exception:
            pass


async def collect(uri, sink, tag, stop):
    """持续接收 WS 消息，data 类型存入 sink"""
    try:
        async with websockets.connect(uri, open_timeout=10) as ws:
            while not stop.is_set():
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                d = json.loads(msg)
                if d.get('type') == 'data':
                    sink.append((tag, d))
                    print(f"    <- {tag} 收到: text={d.get('data')!r} hex={d.get('hex_data')!r}")
    except Exception as e:
        print(f"    !! {tag} WS 异常: {e}")


async def main():
    kill_all()
    time.sleep(1)

    print('1) 启动两个实例')
    p1 = subprocess.Popen([EXE], cwd=CWD)
    time.sleep(6)
    p2 = subprocess.Popen([EXE], cwd=CWD)
    time.sleep(6)
    print('   health1:', http(BASE1, 'GET', '/health'))
    print('   health2:', http(BASE2, 'GET', '/health'))

    print('2) 实例1 起 TCP Server :6100')
    r1 = http(BASE1, 'POST', '/api/net/connect',
              {'mode': 'server', 'protocol': 'tcp', 'host': '0.0.0.0', 'port': TCP_PORT})
    cid1 = r1.get('connection_id')
    print('   connection_id:', cid1, r1.get('message'))

    print('3) 实例2 作 TCP Client 连入')
    r2 = http(BASE2, 'POST', '/api/net/connect',
              {'mode': 'client', 'protocol': 'tcp', 'host': '127.0.0.1', 'port': TCP_PORT})
    cid2 = r2.get('connection_id')
    print('   connection_id:', cid2, r2.get('message'))

    print('4) 建立两端 WebSocket（驱动数据接收）')
    stop = asyncio.Event()
    sink1, sink2 = [], []
    t1 = asyncio.create_task(collect(f'ws://127.0.0.1:20001/ws/net/{cid1}?encoding=utf-8', sink1, '实例1', stop))
    t2 = asyncio.create_task(collect(f'ws://127.0.0.1:20002/ws/net/{cid2}?encoding=utf-8', sink2, '实例2', stop))
    await asyncio.sleep(2.0)
    print('   实例1 客户端列表:', http(BASE1, 'GET', f'/api/net/clients/{cid1}').get('data'))

    results = []

    async def send(base, cid, data, fmt, desc, expect_hex, sink, secs=1.6):
        before = len(sink)
        r = http(base, 'POST', f'/api/net/send/{cid}',
                 {'data': data, 'format': fmt, 'encoding': 'utf-8', 'end_chars': '',
                  'append_check': None, 'target': None})
        await asyncio.sleep(secs)
        got = sink[before:]
        if got:
            actual = got[0][1].get('hex_data', '')
            ok = actual.upper().replace(' ', '') == expect_hex.upper().replace(' ', '')
            print(f"   {'PASS' if ok else 'FAIL'} {desc}: 期望 {expect_hex} / 实际 {actual} (send={r.get('success')})")
            results.append((desc, ok))
        else:
            print(f"   FAIL {desc}: 未收到数据 (send={r})")
            results.append((desc, False))

    print('5) 实例2 -> 实例1（文本）')
    await send(BASE2, cid2, 'hello-2', 'text', '文本 hello-2', '68 65 6C 6C 6F 2D 32', sink1)

    print('6) 实例1 -> 实例2（HEX 偶数）')
    await send(BASE1, cid1, '0102', 'hex', 'HEX 0102', '01 02', sink2)

    print('7) 实例2 -> 实例1（HEX 奇数 "1"）')
    await send(BASE2, cid2, '1', 'hex', 'HEX 奇数 1', '01', sink1)

    print('8) 实例1 -> 实例2（中文）')
    await send(BASE1, cid1, '你好', 'text', '中文 你好', 'E4 BD A0 E5 A5 BD', sink2)

    print('9) 实例2 -> 实例1（带结束符 \\r\\n）')
    before = len(sink1)
    http(BASE2, 'POST', f'/api/net/send/{cid2}',
         {'data': 'AT', 'format': 'text', 'encoding': 'utf-8', 'end_chars': '\r\n',
          'append_check': None, 'target': None})
    await asyncio.sleep(1.6)
    got = sink1[before:]
    ok = bool(got) and got[0][1].get('hex_data', '').upper().replace(' ', '') == '41540D0A'
    print(f"   {'PASS' if ok else 'FAIL'} 结束符 \\r\\n: 实际 {got[0][1].get('hex_data') if got else '无'}")
    results.append(('结束符 \\r\\n', ok))

    print('10) 断开')
    print('   ', http(BASE2, 'POST', f'/api/net/disconnect/{cid2}'))
    print('   ', http(BASE1, 'POST', f'/api/net/disconnect/{cid1}'))

    stop.set()
    t1.cancel()
    t2.cancel()

    print('\n===== 结果汇总 =====')
    for d, ok in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {d}")
    print(f"  共 {len(results)} 项，通过 {sum(1 for _, o in results if o)} 项")

    kill_all()
    try:
        p1.kill(); p2.kill()
    except Exception:
        pass


if __name__ == '__main__':
    asyncio.run(main())
