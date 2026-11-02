const assert = require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
class Node {
  constructor(){this.children=[];this.style={setProperty:(k,v)=>{this.style[k]=v}};this.dataset={};this.className='';this.hidden=false;this.textContent='';this.parent=null;this.classList={add:c=>{this.className+=' '+c},remove:c=>{this.className=this.className.replace(' '+c,'')}}}
  append(...items){for(const item of items){item.parent=this;this.children.push(item)}}
  replaceChildren(...items){this.children=[];this.append(...items)}
  remove(){this.parent.children=this.parent.children.filter(x=>x!==this)}
  get firstElementChild(){return this.children[0]}
}
const root=new Node(),banner=new Node(),scene=new Node(),backdrops=new Node(),fullbg=new Node();const document={getElementById:id=>id==='objects'?root:id==='revealBanner'?banner:id==='backdrops'?backdrops:id==='fullbg'?fullbg:scene,createElement:()=>new Node()};
let state={approved:[{id:1,image:'old',behavior:'still',creator:'Old',x:10,y:20}]},failed=false,id=0;const timers=new Map();
const context={document,URLSearchParams,location:{search:'?room=ABC234'},AbortSignal,encodeURIComponent,
 fetch:async url=>{assert.equal(url,'/api/rooms/ABC234');if(failed)throw Error('offline');return{ok:true,json:async()=>state}},
 setTimeout:(fn,ms)=>{const n=++id;timers.set(n,{fn,ms});return n},clearTimeout:n=>timers.delete(n)};
vm.runInNewContext(fs.readFileSync('output.js','utf8'),context);
const settle=()=>new Promise(resolve=>setImmediate(resolve));
const fire=async ms=>{const entry=[...timers].find(([,v])=>v.ms===ms);assert.ok(entry,`timer ${ms}`);timers.delete(entry[0]);entry[1].fn();await settle()};
const item=(id,creator)=>({id,image:'data:image/png;base64,AA',behavior:'rain',creator,x:25,y:70});
(async()=>{await settle();assert.equal(root.children.length,1);assert.equal(banner.textContent,'');assert.equal(scene.dataset.theme,'neon');
 state={theme:'space',approved:[item(1,'Old'),item(2,'Alice'),item(3,'Bob')]};await fire(1000);assert.equal(scene.dataset.theme,'space');assert.equal(root.children.length,3);assert.match(banner.textContent,/Alice/);assert.ok(root.children[1].firstElementChild.className.includes('reveal-pop'));
 await fire(3000);assert.match(banner.textContent,/Bob/);
 state={approved:[item(1,'Old'),item(2,'Alice')]};await fire(1000);assert.equal(banner.hidden,true);assert.equal(root.children.length,2);
 state={approved:[]};await fire(1000);assert.equal(root.children.length,0);assert.equal(banner.hidden,true);
 state={approved:[item(4,'Carol')]};await fire(1000);assert.match(banner.textContent,/Carol/);
 failed=true;await fire(1000);assert.equal(root.children.length,0);assert.equal(banner.hidden,true);
 failed=false;await fire(1000);assert.equal(root.children.length,1);assert.equal(banner.hidden,true);
 state={approved:[item(4,'Carol'),{...item(9,'Zed'),placement:'full'},{...item(10,'Yan'),placement:'backdrop',scale:2}]};await fire(1000);
 assert.equal(root.children.length,1);assert.equal(backdrops.children.length,1);assert.equal(fullbg.children.length,1);
 assert.match(fullbg.children[0].className,/full/);assert.match(backdrops.children[0].className,/backdrop/);assert.equal(backdrops.children[0].style['--s'],2);
 state={approved:[item(4,'Carol')]};await fire(1000);assert.equal(backdrops.children.length,0);assert.equal(fullbg.children.length,0);
 failed=true;await fire(1000);assert.equal(root.children.length,0);
 console.log('PASS: startup does not replay; approvals reveal in sequence; removal, clear, and disconnect dismiss; reconnect does not replay.');
})().catch(error=>{console.error(error);process.exitCode=1});
