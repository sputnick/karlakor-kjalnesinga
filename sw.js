// Keeps index.html (which contains every lyric) so the page opens with no connection.
// Opening is always instant from the saved copy; a newer copy is fetched in the background
// only when the browser reports it is online, and is kept only if the fetch really succeeded.
const CACHE='kk-page-v1';
const PAGE=new URL('index.html',self.registration.scope).href;   // one key, whatever the URL or query

self.addEventListener('install',e=>{
  e.waitUntil(caches.open(CACHE).then(c=>c.add(new Request(PAGE,{cache:'reload'}))).then(()=>self.skipWaiting()));
});
self.addEventListener('activate',e=>{
  e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));
});

// Fetch the live page and keep it if it changed. Never throws; offline or a bad response is a quiet no-op.
async function refresh(){
  if(!self.navigator.onLine)return false;
  try{
    const res=await fetch(PAGE,{cache:'reload'});
    if(!res.ok)return false;
    const c=await caches.open(CACHE),old=await c.match(PAGE);
    const [a,b]=await Promise.all([old?old.clone().text():null,res.clone().text()]);
    if(a===b)return false;
    await c.put(PAGE,res);
    (await self.clients.matchAll()).forEach(w=>w.postMessage({type:'kk-updated'}));
    return true;
  }catch(err){return false;}
}

self.addEventListener('fetch',e=>{
  if(e.request.mode!=='navigate')return;
  const forced=new URL(e.request.url).searchParams.has('v');   // the version stamp's reload asks for the live copy
  let done;e.waitUntil(new Promise(r=>done=r));
  e.respondWith((async()=>{
    try{
      const c=await caches.open(CACHE);
      if(forced)await refresh();
      const hit=await c.match(PAGE);
      if(!hit)return await fetch(e.request);
      if(!forced)refresh().then(done,done);else done();
      return hit;
    }finally{setTimeout(done,20000);}
  })());
});
