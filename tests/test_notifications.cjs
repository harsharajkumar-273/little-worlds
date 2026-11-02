const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element {
 constructor(id=''){this.id=id;this.dataset={};this.style={};this.textContent='';this.listeners={};this.children=[];this.hidden=false;this.classList={values:new Set(),add:x=>this.classList.values.add(x),remove:x=>this.classList.values.delete(x),toggle(){}}}
 addEventListener(type,fn){this.listeners[type]=fn} append(...nodes){for(const node of nodes){this.children.push(node);if(node.id)elements[node.id]=node}} replaceChildren(...nodes){this.children=nodes} setAttribute(){} removeAttribute(){} getContext(){return {clearRect(){}}} focus(){} select(){}
}
const elements={},get=id=>elements[id]||(elements[id]=new Element(id));
const document={title:'Little Worlds — Studio',body:new Element('body'),getElementById:get,createElement:()=>new Element(),querySelectorAll:()=>[],addEventListener(){}};
let tones=0;class AudioContext{constructor(){this.state='suspended';this.currentTime=0;this.destination={}}async resume(){this.state='running'}createOscillator(){return{frequency:{setValueAtTime(){}},connect(){},start(){tones++},stop(){}}}createGain(){return{gain:{setValueAtTime(){},exponentialRampToValueAtTime(){}},connect(){}}}}
const requests=[],timers=new Map();let timerId=0;
const context={document,window:{AudioContext},navigator:{},cancelAnimationFrame(){},requestAnimationFrame(){return 0},location:{origin:'http://localhost:8765',search:''},URL,URLSearchParams,sessionStorage:{getItem(){return null},setItem(){},removeItem(){}},setInterval(){},setTimeout(fn){let id=++timerId;timers.set(id,fn);return id},clearTimeout(id){timers.delete(id)},fetch:(url,options)=>new Promise(resolve=>requests.push({url,resolve}))};
context.Event=class{constructor(type){this.type=type}};vm.createContext(context);vm.runInContext(fs.readFileSync('promptkit.js','utf8'),context);context.LittleWorldsPrompts=context.window.LittleWorldsPrompts;vm.runInContext(fs.readFileSync('app.js','utf8'),context);
const state=pending=>({approved:[],pending,paused:false,theme:'neon',twitch:{},chat_creation:{}});
const resolve=async(index,pending)=>{requests[index].resolve({ok:true,json:async()=>state(pending)});await new Promise(r=>setImmediate(r))};
const item=id=>({id,creator:'Viewer',description:'cat',behavior:'still',x:20,y:30,image:'test'});
(async()=>{
 vm.runInContext("enter('streamer','ABC234','secret')",context);await resolve(0,[item(1)]);
 assert.equal(document.title,'(1) Little Worlds — Studio');assert.equal(elements.queueToast,undefined);
 await get('enableSound').listeners.click();assert.equal(get('soundStatus').textContent,'Notification sound enabled for this window.');
 vm.runInContext('update()',context);await resolve(1,[item(1),item(2)]);
 assert.match(get('queueToast').textContent,/Viewer: cat/);assert.equal(tones,1);
 vm.runInContext('update()',context);vm.runInContext('update()',context);
 await resolve(3,[item(1)]);assert.equal(document.title,'(1) Little Worlds — Studio');
 await resolve(2,[item(1),item(2)]);assert.equal(document.title,'(1) Little Worlds — Studio');assert.equal(tones,1);
 vm.runInContext('update()',context);get('leave').listeners.click();assert.equal(document.title,'Little Worlds — Studio');assert.equal(get('queueToast').textContent,'');assert.equal(get('queueToast').classList.values.has('show'),false);
 await resolve(4,[item(9)]);assert.equal(document.title,'Little Worlds — Studio');assert.equal(get('queueToast').textContent,'');
 console.log('PASS: initial title, user-enabled audio, toast cleanup, stale responses, and role-change privacy.');
})().catch(e=>{console.error(e);process.exitCode=1});
