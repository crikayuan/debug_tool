# -*- coding: utf-8 -*-
"""专门复现「两实例连同一 Broker」场景（AC-11）：ClientID 唯一性 + 双方同时收报不互踢。"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
import asyncio, json, os, subprocess, time, urllib.request, urllib.error, uuid, websockets

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.normpath(os.path.join(HERE, "..", "backend"))
PEER = os.path.join(HERE, "mqtt_peer.py")
HOST, PORT = "broker.emqx.io", 1883
_NP = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def log(*a): print(*a, flush=True)

def http(base, m, p, body=None, t=25):
    d = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base+p, data=d, headers={"Content-Type":"application/json"} if d else {}, method=m)
    try:
        with _NP.open(req, timeout=t) as r: return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}
    except Exception as e: return -1, {"detail":str(e)}

def start(port):
    code=("import sys;sys.path.insert(0,'.');import uvicorn;from main import app;"
          f"uvicorn.run(app,host='127.0.0.1',port={port},log_level='warning',access_log=False)")
    return subprocess.Popen([sys.executable,"-c",code],cwd=BACKEND)

def health(base,to=25):
    dl=time.time()+to
    while time.time()<dl:
        if http(base,"GET","/health",3)[0]==200: return True
        time.sleep(0.4)
    return False

async def collect(url,sink,stop):
    try:
        async with websockets.connect(url,open_timeout=15,max_size=None) as ws:
            while not stop.is_set():
                try: raw=await asyncio.wait_for(ws.recv(),timeout=1.0)
                except asyncio.TimeoutError: continue
                d=json.loads(raw)
                if d.get("type")=="data": sink.append(d)
                elif d.get("type")=="error": sink.append({"__err": d})
    except Exception as e: log("  WS任务异常:", e)

def pub(topic,payload,qos=1,count=1):
    return subprocess.run([sys.executable,PEER,"--host",HOST,"--port",str(PORT),"--topic",topic,
        "--mode","pub","--payload",payload,"--format","hex","--qos",str(qos),"--count",str(count)],
        capture_output=True,text=True,timeout=60)

async def main():
    base="http://127.0.0.1:20031"; base2="http://127.0.0.1:20032"
    p1=start(20031); p2=start(20032)
    if not health(base) or not health(base2):
        log("后端未就绪"); p1.kill(); p2.kill(); return
    suf=uuid.uuid4().hex[:6]; topic=f"qa/multi/{suf}/t"
    st,r1=http(base,"POST","/api/mqtt/connect",{"host":HOST,"port":PORT})
    st,r2=http(base2,"POST","/api/mqtt/connect",{"host":HOST,"port":PORT})
    cidA=r1["data"]["connection_id"]; idA=r1["data"]["client_id"]
    cidB=r2["data"]["connection_id"]; idB=r2["data"]["client_id"]
    log(f"A: cid={cidA} client_id={idA}")
    log(f"B: cid={cidB} client_id={idB}")
    log(f"ClientID 唯一: {idA != idB}")

    http(base,"POST",f"/api/mqtt/subscribe/{cidA}",{"topic":topic,"qos":1})
    http(base2,"POST",f"/api/mqtt/subscribe/{cidB}",{"topic":topic,"qos":1})
    await asyncio.sleep(2.0)
    log("A subs:", http(base,"GET",f"/api/mqtt/subscriptions/{cidA}")[1].get("data"))
    log("B subs:", http(base2,"GET",f"/api/mqtt/subscriptions/{cidB}")[1].get("data"))

    sinkA=[]; sinkB=[]; stopA=asyncio.Event(); stopB=asyncio.Event()
    tA=asyncio.create_task(collect(base.replace("http","ws")+f"/ws/mqtt/{cidA}?encoding=utf-8",sinkA,stopA))
    tB=asyncio.create_task(collect(base2.replace("http","ws")+f"/ws/mqtt/{cidB}?encoding=utf-8",sinkB,stopB))
    await asyncio.sleep(2.5)

    for i in range(3):
        await asyncio.to_thread(pub,topic,f"0{i+1}",1,1)
        await asyncio.sleep(1.5)
    await asyncio.sleep(2.0)

    def tp(s): return [d.get("topic") for d in s if d.get("topic")]
    gotA=sum(1 for d in sinkA if d.get("topic")==topic)
    gotB=sum(1 for d in sinkB if d.get("topic")==topic)
    log(f"发布 3 条 → A收到={gotA}  B收到={gotB}")
    log(f"A 帧topic={tp(sinkA)}  B 帧topic={tp(sinkB)}")
    log("A connected:", http(base,"GET",f"/api/mqtt/status/{cidA}")[1].get("connected"))
    log("B connected:", http(base2,"GET",f"/api/mqtt/status/{cidB}")[1].get("connected"))
    log("A stats:", http(base,"GET",f"/api/mqtt/status/{cidA}")[1].get("stats"))
    log("B stats:", http(base2,"GET",f"/api/mqtt/status/{cidB}")[1].get("stats"))

    stopA.set(); stopB.set(); tA.cancel(); tB.cancel()
    http(base,"POST",f"/api/mqtt/disconnect/{cidA}")
    http(base2,"POST",f"/api/mqtt/disconnect/{cidB}")
    p1.kill(); p2.kill()
    log("DONE")

asyncio.run(main())
