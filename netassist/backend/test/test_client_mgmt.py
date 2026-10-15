import sys, time, socket
sys.path.insert(0, ".")
from models import NetConfig
from services.net_service import net_manager

config = NetConfig(mode="server", protocol="tcp", host="127.0.0.1", port=9002)
res = net_manager.create_connection(config)
cid = res.data["connection_id"]
print("cid:", cid)

c1 = socket.create_connection(("127.0.0.1", 9002))
c2 = socket.create_connection(("127.0.0.1", 9002))

# 轮询 read_data 触发 accept
for _ in range(15):
    r = net_manager.read_data(cid)
    if r:
        print("read:", r)
    time.sleep(0.05)

clients = net_manager.get_clients(cid)
print("clients:", clients)
assert len(clients) == 2, "客户端数量应为 2"

# c1 发数据
c1.send(b"hello-from-c1")
time.sleep(0.1)
for _ in range(8):
    r = net_manager.read_data(cid)
    if r:
        cid_src, data = r
        print("数据来源 client_id:", cid_src, "内容:", data)
        assert cid_src is not None, "应带客户端标识"
    time.sleep(0.05)

# 定向发送给第一个客户端
first_id = clients[0]["id"]
second_id = clients[1]["id"]
net_manager.send_data(cid, b"only-c1", first_id)
time.sleep(0.1)
print("c1 recv(定向):", c1.recv(1024))

# 广播
net_manager.send_data(cid, b"broadcast-all", "all")
time.sleep(0.1)
print("c1 recv(广播):", c1.recv(1024))
print("c2 recv(广播):", c2.recv(1024))

# 多选定向
net_manager.send_data(cid, b"multi", first_id + "," + second_id)
time.sleep(0.1)
print("c1 recv(多选):", c1.recv(1024))
print("c2 recv(多选):", c2.recv(1024))

# 断开单个客户端
r = net_manager.disconnect_client(cid, second_id)
print("断开 c2:", r.success, r.message)
print("剩余 clients:", net_manager.get_clients(cid))

net_manager.disconnect(cid)
c1.close()
print("=== 客户端管理测试通过 ===")
