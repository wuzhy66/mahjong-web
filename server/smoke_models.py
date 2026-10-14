import time
from server.policies import Policies
from server.rooms import Room
from mjenv.spaces import to_id
p=Policies(); start=time.time(); p.prepare(['easy','medium','hard']); print('models loaded',time.time()-start,flush=True)
r=Room('hangzhou',['easy','medium','hard'],p,seed=297)
for i in range(1200):
    seat,acts=r.core.peek()
    if seat is None: break
    if seat==0: r.step(to_id(p.choose('medium',r.core.game,seat,acts),acts))
    else: r.step()
assert r.core.finished and sum(r.scores)==0
print({'steps':i,'seconds':time.time()-start,'result':r.core.result},flush=True)
