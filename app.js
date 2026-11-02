'use strict';
const $ = id => document.getElementById(id);
const canvas=$('drawing'),ctx=canvas.getContext('2d'),scene=$('scene'),objects=$('objects'),backdrops=$('backdrops'),fullbg=$('fullbg'),marker=$('placement');
let color='#f8f4ff',erasing=false,drawing=false,behavior='still',position={x:22,y:32};
let library=[],sizeFocus=null,aiArt=false,role='',code='',key='',viewerToken='',warningCount=0,submitting=false,pending=[],approved=[],selected=null,paused=false,reviewId=null,dragging=false,lastState='',twitchConnected=false,twitchAnnouncements=false,chatEnabled=false,savingPlacement=false;
let updateSequence=0,appliedSequence=0,sessionEpoch=0;
const clamp=(n,min,max)=>Math.min(max,Math.max(min,n));
async function api(path,method='GET',data){const headers={};if(key)headers['X-Streamer-Key']=key;if(viewerToken)headers['X-Viewer-Token']=viewerToken;if(data!==undefined)headers['Content-Type']='application/json';const response=await fetch(path,{method,headers,body:data===undefined?undefined:JSON.stringify(data),cache:'no-store'});const result=await response.json();if(!response.ok){const error=new Error(result.error||'Request failed');error.warnings=result.warnings;error.previews_left=result.previews_left;throw error;}return result;}
const route=(suffix='')=>`/api/rooms/${encodeURIComponent(code)}${suffix}`;
function showError(error){if(role==='viewer'){if(Number.isInteger(error.warnings))warningCount=error.warnings;updateViewerControls();$('status').textContent=error.message}else $('sceneHelp').textContent=error.message;}
function updateViewerControls(){$('warnings').textContent=`Warnings: ${warningCount} of 3`;$('submit').disabled=paused||warningCount>=3||submitting;}
async function update(force=false){if(!role||dragging)return;const sequence=++updateSequence,epoch=sessionEpoch;try{const state=await api(route(role==='streamer'?'/review':''));if(epoch!==sessionEpoch||sequence<appliedSequence)return;appliedSequence=sequence;const signature=JSON.stringify(state);if(!force&&signature===lastState)return;lastState=signature;approved=state.approved;pending=state.pending||[];library=state.library||[];if(role==='streamer')notifyNew();paused=state.paused;applyTheme(state.theme);if(role==='streamer'){$('viewerUrl').value=state.viewer_url||'';$('copyViewer').disabled=!state.viewer_url;$('chatInviteHint').textContent=state.viewer_url?'The invitation uses the configured viewer link; it requires the tunnel to be running.':'Chat will receive a local-only test code until remote access is configured.';$('viewerLinkStatus').textContent=state.viewer_url?'Viewer link configured; it works only while the approved tunnel runs.':'Remote viewer access is not configured.';const twitch=state.twitch||{};twitchConnected=!!twitch.connected;twitchAnnouncements=!!twitch.announcements;const chat=state.chat_creation||{};chatEnabled=!!chat.enabled;$('toggleChatCreation').disabled=!twitchConnected;$('toggleChatCreation').textContent=chatEnabled?'Pause !draw':'Enable !draw';$('chatCreationStatus').textContent=`${chat.status||'off'} · ${chat.attempts||0} of ${chat.limit||10} generation attempts used`;$('shareTwitch').disabled=!twitchConnected;$('toggleAnnouncements').disabled=!twitchConnected;$('toggleAnnouncements').textContent=`Announcements: ${twitchAnnouncements?'on':'off'}`;if(twitchConnected){$('twitchStatus').textContent=`Connected as ${twitch.login}. Chat messages use this account.`;$('twitchAuthorize').hidden=true}}if(!pending.some(x=>x.id===reviewId))reviewId=pending[0]?.id??null;if(!approved.some(x=>x.id===selected))selected=null;if(!sizeTarget()&&reviewId!==null)sizeFocus={kind:'pending',id:reviewId};render();}catch(e){if(epoch===sessionEpoch&&sequence>=appliedSequence)showError(e)}}
const THEME_NAMES={neon:'Neon Night',space:'Deep Space',sunset:'Sunset',forest:'Forest',ocean:'Ocean',studio:'Cozy Studio',green:'Green Screen',clear:'Transparent'};
function applyTheme(theme){const chosen=THEME_NAMES[theme]?theme:'neon';scene.dataset.theme=chosen;$('sceneTitle').textContent=THEME_NAMES[chosen];document.querySelectorAll('.theme-option').forEach(button=>{const active=button.dataset.theme===chosen;button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active))})}
document.querySelectorAll('.theme-option').forEach(button=>button.addEventListener('click',()=>{if(role==='streamer')action('/theme',{theme:button.dataset.theme})}));
function enter(mode,room,secret=''){sessionEpoch++;role=mode;code=room;key=secret;lastState='';$('entry').hidden=true;$('studio').hidden=false;document.body.classList.toggle('role-viewer',mode==='viewer');document.body.classList.toggle('role-streamer',mode==='streamer');$('roomCode').textContent=code;const obsUrl=new URL('/output',location.origin);obsUrl.searchParams.set('room',code);$('obsUrl').value=obsUrl.href;$('roleLabel').textContent=mode==='viewer'?'VIEWER':'STREAMER · KEEP THIS WINDOW PRIVATE';$('sceneHelp').textContent=mode==='viewer'?'Approved objects appear here.':'Drag approved objects to move them';if(mode==='streamer')sessionStorage.setItem('littleWorldsStreamer',JSON.stringify({code,key}));$('polishField').hidden=!(mode==='viewer'&&aiArt);update(true);}
$('createRoom').addEventListener('click',async()=>{try{const room=await api('/api/rooms','POST',{});enter('streamer',room.code,room.key)}catch(e){$('entryStatus').textContent=e.message}});
$('joinRoom').addEventListener('click',async()=>{const room=$('roomInput').value.trim().toUpperCase();if(!/^[A-Z2-9]{6}$/.test(room)){$('entryStatus').textContent='Enter the six-character room code.';return}try{viewerToken=sessionStorage.getItem(`littleWorldsViewer:${room}`)||'';const joined=await api(`/api/rooms/${encodeURIComponent(room)}/join`,'POST',{});viewerToken=joined.viewer_token;warningCount=joined.warnings;aiArt=!!joined.ai_art;sessionStorage.setItem(`littleWorldsViewer:${room}`,viewerToken);enter('viewer',room)}catch(e){viewerToken='';$('entryStatus').textContent=e.message}});
$('leave').addEventListener('click',()=>{webcamOff();sessionEpoch++;resetSessionWork();resetNotifications();if(role==='streamer')sessionStorage.removeItem('littleWorldsStreamer');role='';code='';key='';viewerToken='';warningCount=0;pending=[];approved=[];reviewId=null;selected=null;$('studio').hidden=true;$('entry').hidden=false;document.body.classList.remove('role-streamer','role-viewer')});
try{const saved=JSON.parse(sessionStorage.getItem('littleWorldsStreamer'));if(document.body.dataset.viewerOnly!=='true'&&saved?.code&&saved?.key)enter('streamer',saved.code,saved.key)}catch(e){sessionStorage.removeItem('littleWorldsStreamer')}
if(document.body.dataset.viewerOnly==='true'){const requested=new URLSearchParams(location.search).get('room')||'';if(/^[A-Z2-9]{6}$/.test(requested))$('roomInput').value=requested;$('entryTitle').textContent='Join the community canvas.';$('entryDescription').textContent='Use the shared room code to create an object for streamer review.';$('entryStatus').textContent='Enter the room code or use the shared viewer link.';}
setInterval(()=>update(),1000);
function point(e){const r=canvas.getBoundingClientRect();return{x:(e.clientX-r.left)*canvas.width/r.width,y:(e.clientY-r.top)*canvas.height/r.height}}
function stroke(e,start=false){const p=point(e);ctx.globalCompositeOperation=erasing?'destination-out':'source-over';ctx.lineWidth=Number($('size').value);ctx.lineCap='round';ctx.lineJoin='round';ctx.strokeStyle=color;if(start){ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(p.x+.01,p.y+.01)}else ctx.lineTo(p.x,p.y);ctx.stroke()}
canvas.addEventListener('pointerdown',e=>{drawing=true;canvas.setPointerCapture(e.pointerId);stroke(e,true)});canvas.addEventListener('pointermove',e=>{if(drawing)stroke(e)});canvas.addEventListener('pointerup',()=>{drawing=false;ctx.closePath()});canvas.addEventListener('pointercancel',()=>{drawing=false;ctx.closePath()});
document.querySelectorAll('.swatch').forEach(b=>b.addEventListener('click',()=>{color=b.dataset.color;erasing=false;$('eraser').classList.remove('active');document.querySelectorAll('.swatch').forEach(x=>x.classList.toggle('active',x===b))}));
$('eraser').addEventListener('click',()=>{erasing=!erasing;$('eraser').classList.toggle('active',erasing)});$('clearDrawing').addEventListener('click',()=>ctx.clearRect(0,0,canvas.width,canvas.height));
document.querySelectorAll('.behavior').forEach(b=>b.addEventListener('click',()=>{behavior=b.dataset.behavior;document.querySelectorAll('.behavior').forEach(x=>x.classList.toggle('active',x===b))}));
function scenePoint(e){const r=scene.getBoundingClientRect();return{x:clamp((e.clientX-r.left)/r.width*100,0,100),y:clamp((e.clientY-r.top)/r.height*100,0,100)}}
scene.addEventListener('pointerdown',e=>{if(role!=='viewer'||e.target.closest('.object:not(.full)'))return;position=scenePoint(e);marker.style.left=position.x+'%';marker.style.top=position.y+'%';$('status').textContent='Placement chosen. Your drawing stays private until approved.'});
function hasDrawing(){return ctx.getImageData(0,0,canvas.width,canvas.height).data.some((v,i)=>i%4===3&&v>0)}
$('submit').addEventListener('click',async()=>{if(paused||submitting||warningCount>=3)return;if(createMode){if(!previewValid()){$('status').textContent='Make your AI creation first (press Create with AI), then send it.';return}}else if(!hasDrawing()){$('status').textContent='Draw something before sending it for review.';return}const creator=$('creator').value.trim();if(!creator){$('status').textContent='Enter your display name before submitting.';return}const description=$('description').value.trim();if(!description){$('status').textContent='Please describe your drawing before submitting.';return}const epoch=sessionEpoch;submitting=true;updateViewerControls();const polish=aiArt&&previewValid();$('status').textContent=polish?'Checking and turning your drawing into art… this can take a minute.':'Checking your submission…';try{const result=await api(route('/submissions'),'POST',{image:createMode?undefined:canvas.toDataURL('image/png'),description,creator,behavior,polish:createMode||polish,mode:createMode?'create':'polish',style:$('artStyle').value,placement:kind,...position});if(epoch!==sessionEpoch)return;warningCount=result.warnings;$('status').textContent='Sent privately! Waiting for streamer review.';clearPreview()}catch(e){showError(e)}finally{submitting=false;updateViewerControls()}});
function art(item){const effect=document.createElement('div');effect.className='effect '+item.behavior;const img=document.createElement('img');img.src=item.image;img.alt='';effect.append(img);return effect}
async function action(suffix,data={},method='POST'){try{const result=await api(route(suffix),method,data);await update(true);if(result.chat_error)$('twitchStatus').textContent=result.chat_error}catch(e){showError(e);await update(true)}}
const layerFor=item=>item.placement==='full'?fullbg:item.placement==='backdrop'?backdrops:objects;
const classFor=item=>item.placement==='full'?' full':item.placement==='backdrop'?' backdrop':'';
function renderScene(){
  [objects,backdrops,fullbg].forEach(layer=>layer.replaceChildren());
  approved.forEach(item=>{
    const node=document.createElement('div');node.className='object'+classFor(item)+(selected===item.id?' selected':'');node.dataset.id=item.id;
    node.style.left=item.x+'%';node.style.top=item.y+'%';node.style.setProperty('--s',item.scale||1);
    node.setAttribute('aria-label',`Approved ${item.placement==='full'?'full background':item.placement==='backdrop'?'background piece':item.behavior+' object'}`);node.append(art(item));
    if(role==='streamer'){
      node.addEventListener('pointerdown',e=>{e.stopPropagation();selected=item.id;sizeFocus={kind:'approved',id:item.id};renderSelection();if(item.placement==='full')return;dragging=true;node.setPointerCapture(e.pointerId)});
      if(item.placement!=='full'){
        node.addEventListener('pointermove',e=>{if(!node.hasPointerCapture(e.pointerId))return;const p=scenePoint(e);item.x=p.x;item.y=p.y;node.style.left=p.x+'%';node.style.top=p.y+'%'});
        node.addEventListener('pointerup',()=>{dragging=false;action(`/objects/${item.id}`,{x:item.x,y:item.y})});
        node.addEventListener('pointercancel',()=>{dragging=false;update(true)});
      }
    }
    layerFor(item).append(node);
  });
  const preview=role==='streamer'&&pending.find(x=>x.id===reviewId);
  if(preview){
    const full=preview.placement==='full',ghost=document.createElement('div');ghost.className='object review-ghost'+classFor(preview);
    ghost.style.left=preview.x+'%';ghost.style.top=preview.y+'%';ghost.style.setProperty('--s',preview.scale||1);ghost.append(art(preview));
    const label=document.createElement('span');label.className='ghost-label';label.textContent='PRIVATE PREVIEW';ghost.append(label);
    if(!full){
      ghost.addEventListener('pointerdown',e=>{e.stopPropagation();dragging=true;ghost.setPointerCapture(e.pointerId)});
      ghost.addEventListener('pointermove',e=>{if(!ghost.hasPointerCapture(e.pointerId))return;const p=scenePoint(e);ghost.style.left=p.x+'%';ghost.style.top=p.y+'%';ghost.dataset.x=p.x;ghost.dataset.y=p.y});
      ghost.addEventListener('pointerup',async()=>{dragging=false;if(ghost.dataset.x===undefined)return;savingPlacement=true;try{await api(route(`/placement/${preview.id}`),'POST',{x:Number(ghost.dataset.x),y:Number(ghost.dataset.y)});await update(true)}catch(e){showError(e);await update(true)}finally{savingPlacement=false}});
      ghost.addEventListener('pointercancel',()=>{dragging=false;update(true)});
    }
    layerFor(preview).append(ghost);
  }
  $('objectCount').textContent=approved.length;renderSelection();
}
function renderSelection(){syncSize();document.querySelectorAll('#scene .object[data-id]').forEach(node=>node.classList.toggle('selected',Number(node.dataset.id)===selected));$('remove').disabled=!approved.some(x=>x.id===selected)}
function renderQueue(){const queue=$('queue');$('queueCount').textContent=pending.length;queue.replaceChildren();if(!pending.length){queue.className='queue-empty';queue.innerHTML='<div class="empty-icon">✉</div><div><strong>Nothing waiting just yet</strong><p>New creations will appear here for your review.</p></div>';return}queue.className='queue-list';pending.forEach(item=>{const row=document.createElement('div');row.className='review-item';const picture=document.createElement('div');picture.className='review-art';picture.append(art(item));const info=document.createElement('div');info.className='review-info';const title=document.createElement('strong');title.textContent=`Submission #${item.id} · ${item.behavior}${item.ai?' · AI art':''}`;const sub=document.createElement('p');sub.textContent=`Position: ${Math.round(item.x)}% across, ${Math.round(item.y)}% down`;const creator=document.createElement('p');creator.textContent=`Created by ${item.creator}`;const description=document.createElement('p');description.textContent=item.description;info.append(title,creator,sub,description);const actions=document.createElement('div');actions.className='review-actions';const view=document.createElement('button');view.className='outline';view.textContent=reviewId===item.id?'Previewing':'Preview';view.addEventListener('click',()=>{reviewId=item.id;selected=null;sizeFocus={kind:'pending',id:item.id};render()});const reject=document.createElement('button');reject.className='outline danger';reject.textContent='Reject';reject.addEventListener('click',()=>action(`/reject/${item.id}`));const approve=document.createElement('button');approve.className='primary';approve.textContent='Approve';approve.addEventListener('click',()=>{if(!savingPlacement&&!dragging)action(`/approve/${item.id}`)});actions.append(view,reject,approve);row.append(picture,info,actions);queue.append(row)})}
function render(){syncSize();renderScene();renderQueue();renderLibrary();$('pause').textContent=paused?'▶  Resume submissions':'Ⅱ  Pause submissions';updateViewerControls();if(paused)$('status').textContent='Submissions are paused by the streamer.'}
$('connectTwitch').addEventListener('click',async()=>{try{const result=await api(route('/twitch/start'),'POST',{});const link=$('twitchAuthorize');link.href=result.url;link.hidden=false;$('twitchStatus').textContent='Open Twitch authorization, then return to this window.'}catch(e){$('twitchStatus').textContent=e.message}});
$('shareTwitch').addEventListener('click',async()=>{try{await api(route('/twitch/share'),'POST',{});$('twitchStatus').textContent='Sent the room invitation to Twitch chat.'}catch(e){$('twitchStatus').textContent=e.message}});
$('toggleAnnouncements').addEventListener('click',async()=>{try{await api(route('/twitch/announcements'),'POST',{enabled:!twitchAnnouncements});await update(true);$('twitchStatus').textContent=`Twitch approval announcements are ${twitchAnnouncements?'on':'off'}.`}catch(e){$('twitchStatus').textContent=e.message}});
$('toggleChatCreation').addEventListener('click',async()=>{try{await api(route('/chat/toggle'),'POST',{enabled:!chatEnabled});await update(true)}catch(e){$('chatCreationStatus').textContent=e.message}});
$('copyViewer').addEventListener('click',async()=>{try{await navigator.clipboard.writeText($('viewerUrl').value);$('viewerLinkStatus').textContent='Copied the viewer link.'}catch(e){$('viewerUrl').focus();$('viewerUrl').select();$('viewerLinkStatus').textContent='Select and copy the viewer link above.'}});
$('copyObs').addEventListener('click',async()=>{try{await navigator.clipboard.writeText($('obsUrl').value);$('obsStatus').textContent='Copied. Add it as a Browser Source below your webcam.'}catch(e){$('obsUrl').focus();$('obsUrl').select();$('obsStatus').textContent='Select and copy the URL above.'}});
$('pause').addEventListener('click',()=>action('/pause',{paused:!paused}));$('remove').addEventListener('click',()=>{if(selected!==null)action(`/objects/${selected}`,{},'DELETE')});$('clearScene').addEventListener('click',()=>action('/clear'));

// Streamer alert: a toast, a short chime and a tab-title badge whenever new submissions reach the review queue.
const baseTitle=document.title;let seenIds=null,audioCtx=null;
function notifyNew(){
  const ids=new Set(pending.map(x=>x.id));
  document.title=pending.length?`(${pending.length}) ${baseTitle}`:baseTitle;
  if(seenIds===null){seenIds=ids;return}
  const fresh=pending.filter(x=>!seenIds.has(x.id));seenIds=ids;
  if(!fresh.length)return;
  const first=fresh[0],who=first.creator?`${first.creator}: `:'';
  let toast=document.getElementById('queueToast');
  if(!toast){toast=document.createElement('div');toast.id='queueToast';toast.setAttribute('role','status');document.body.append(toast)}
  toast.textContent=fresh.length>1?`${fresh.length} new creations waiting for review`:`New creation waiting — ${who}${first.description}`;
  toast.classList.add('show');clearTimeout(notifyNew.timer);notifyNew.timer=setTimeout(()=>toast.classList.remove('show'),6000);
  try{
    if(!audioCtx||audioCtx.state!=='running'){if(audioCtx)$('soundStatus').textContent='Sound is paused. Select Enable notification sound to resume.';return}
    const osc=audioCtx.createOscillator(),gain=audioCtx.createGain();
    osc.type='sine';osc.frequency.setValueAtTime(660,audioCtx.currentTime);osc.frequency.setValueAtTime(880,audioCtx.currentTime+.12);
    gain.gain.setValueAtTime(.15,audioCtx.currentTime);gain.gain.exponentialRampToValueAtTime(.001,audioCtx.currentTime+.35);
    osc.connect(gain);gain.connect(audioCtx.destination);osc.start();osc.stop(audioCtx.currentTime+.35);
  }catch(_){}
}

function resetNotifications(){
  seenIds=null;document.title=baseTitle;
  clearTimeout(notifyNew.timer);
  const toast=document.getElementById('queueToast');
  if(toast){toast.classList.remove('show');toast.textContent=''}
}
$('enableSound').addEventListener('click',async()=>{
  try{
    const AudioContextType=window.AudioContext||window.webkitAudioContext;
    if(!AudioContextType)throw new Error('Audio is unavailable');
    audioCtx=audioCtx||new AudioContextType();
    if(audioCtx.state!=='running')await audioCtx.resume();
    if(audioCtx.state!=='running')throw new Error('Audio is unavailable');
    $('soundStatus').textContent='Notification sound enabled for this window.';
    $('enableSound').textContent='Notification sound enabled';
  }catch(_){$('soundStatus').textContent='Sound unavailable. Check your browser and try again.'}
});

// AI preview: the viewer sees the generated art privately and can redo it before sending anything for review.
// Two modes: polish a sketch, or create from the description alone (no drawing needed).
let kind='object';
const KIND_HELP={object:'A thing that sits in the scene and moves. Tap the scene to choose its spot.',backdrop:'A piece of scenery (a building, tree or hill) that sits behind everyone and everything. Tap the scene to choose where; the streamer can resize it.',full:'Replaces the whole background. It is always still, and a new full background replaces the old one.'};
let previewArt='',previewKind='',previewImage='',previewDesc='',previewMode='',previewStyle='',previewing=false,createMode=false;
const modeNow=()=>createMode?'create':'polish';
function previewValid(){return !!previewArt&&previewMode===modeNow()&&previewStyle===$('artStyle').value&&previewKind===kind&&previewDesc===$('description').value.trim()&&(createMode||previewImage===canvas.toDataURL('image/png'))}
function clearPreview(){previewArt=previewImage=previewDesc=previewMode=previewStyle=previewKind='';renderPreview()}
function setMode(create){createMode=create;$('modeCreate').classList.toggle('active',create);$('modePolish').classList.toggle('active',!create);
  $('modeHelp').textContent=create?'No sketch needed: the AI creates a new object from your description. Be specific, e.g. "a smiling cloud wearing sunglasses".':'Redraws your sketch in the style you pick. Add a description so the AI knows what it is.';renderPreview()}
function renderPreview(){
  const has=!!previewArt,valid=previewValid();
  $('previewImg').hidden=!has;$('previewEmpty').hidden=has;$('previewImg').classList.toggle('stale',has&&!valid);
  if(has)$('previewImg').src=previewArt;
  $('useOriginal').hidden=!has||createMode;
  $('previewArt').textContent=previewing?'Making your art…':has?'✨ Try another version':createMode?'🎨 Create with AI':'✨ Preview with AI';
  $('previewNote').textContent=!has?(createMode?'Press Create with AI, then send the result.':'Sending now uses your own drawing.'):valid?'Sending now uses this AI art. Not happy? Try another version.':createMode?'Your description or style changed, so this is out of date. Create it again.':'You changed your drawing, description or style, so this AI art is out of date. Preview again, or send your own drawing.';
}
$('previewArt').addEventListener('click',async()=>{
  if(previewing||paused||warningCount>=3)return;
  if(!createMode&&!hasDrawing()){$('status').textContent='Draw something first, or switch to Create from words.';return}
  const creator=$('creator').value.trim(),description=$('description').value.trim();
  if(!creator){$('status').textContent='Enter your display name first.';return}
  if(!description){$('status').textContent=createMode?'Describe what you want the AI to create.':'Describe your drawing first so the AI knows what it is.';return}
  const image=createMode?'':canvas.toDataURL('image/png'),style=$('artStyle').value,mode=modeNow(),chosen=kind;
  const epoch=sessionEpoch;previewing=true;$('previewArt').disabled=true;renderPreview();$('status').textContent='Checking and making your AI art… this can take up to a minute.';
  try{
    const result=await api(route('/preview'),'POST',{image:createMode?undefined:image,description,creator,mode,style,placement:chosen});if(epoch!==sessionEpoch)return;
    previewArt=result.art;previewImage=image;previewDesc=description;previewMode=mode;previewStyle=style;previewKind=chosen;
    $('previewLeft').textContent=`${result.previews_left} AI ${result.previews_left===1?'try':'tries'} left. Nothing is sent until you press Send for review.`;
    $('status').textContent='Here is your AI art. Send it, try another version, or change your words.';
  }catch(e){if(epoch!==sessionEpoch)return;showError(e);if(Number.isInteger(e.previews_left))$('previewLeft').textContent=`${e.previews_left} AI tries left.`}
  finally{previewing=false;$('previewArt').disabled=false;renderPreview()}
});
$('useOriginal').addEventListener('click',()=>{clearPreview();$('status').textContent='Okay — sending will use your own drawing.'});
$('modePolish').addEventListener('click',()=>setMode(false));$('modeCreate').addEventListener('click',()=>setMode(true));
$('artStyle').addEventListener('change',renderPreview);
document.querySelectorAll('.kind').forEach(b=>b.addEventListener('click',()=>{kind=b.dataset.kind;document.querySelectorAll('.kind').forEach(x=>x.classList.toggle('active',x===b));$('kindHelp').textContent=KIND_HELP[kind];renderPreview()}));
canvas.addEventListener('pointerup',renderPreview);$('clearDrawing').addEventListener('click',renderPreview);$('description').addEventListener('input',renderPreview);

// Streamer: resize the selected scene object, or the waiting creation being previewed, before or after approval.
function sizeTarget(){const f=sizeFocus;if(!f)return null;return(f.kind==='approved'?approved:pending).find(x=>x.id===f.id)||null}
function syncSize(){const t=sizeTarget(),ok=!!t&&t.placement!=='full',pct=Math.round((t?.scale||1)*100);$('objSize').disabled=!ok;$('objSize').value=pct;$('objSizeValue').textContent=ok?pct+'%':t?'full background':'—'}
$('objSize').addEventListener('pointerdown',()=>{dragging=true});
$('objSize').addEventListener('input',()=>{const t=sizeTarget();if(!t)return;t.scale=Number($('objSize').value)/100;$('objSizeValue').textContent=$('objSize').value+'%';renderScene()});
$('objSize').addEventListener('change',()=>{dragging=false;const t=sizeTarget();if(!t)return;action(`/${approved.includes(t)?'objects':'placement'}/${t.id}`,{scale:t.scale})});

// Streamer webcam preview. "Show only me" cuts the person out of the camera picture (MediaPipe, run in this tab, nothing
// is uploaded) so the scene background shows instead of your room. If the model cannot load, the plain camera is shown.
let webcamToken=0,webcamStream=null,segmenter=null,segmenterFailed=false,cutLoop=0;
async function loadSegmenter(){
  if(segmenter)return segmenter;
  const {ImageSegmenter,FilesetResolver}=await import('/vendor/mediapipe/vision_bundle.mjs');
  const files=await FilesetResolver.forVisionTasks('/vendor/mediapipe/wasm');
  const make=delegate=>ImageSegmenter.createFromOptions(files,{baseOptions:{modelAssetPath:'/vendor/mediapipe/selfie_segmenter.tflite',delegate},runningMode:'VIDEO',outputConfidenceMasks:true,outputCategoryMask:false});
  // The GPU mode can load yet fail on first use (no WebGL, blocked GPU). Run one tiny frame to find out, and fall back to CPU.
  const probe=document.createElement('canvas');probe.width=probe.height=64;
  const works=async delegate=>{const made=await make(delegate);try{made.segmentForVideo(probe,performance.now(),()=>{});return made}catch(e){made.close?.();throw e}};
  try{segmenter=await works('GPU')}catch(_){segmenter=await works('CPU')}
  return segmenter;
}
function runCutout(){
  const video=$('webcamVideo'),canvas=$('webcamCanvas'),ctx=canvas.getContext('2d',{willReadFrequently:true});
  let lastTime=-1,frame=0,invert=false;
  const tick=()=>{
    cutLoop=requestAnimationFrame(tick);
    if(!webcamStream||video.readyState<2||video.currentTime===lastTime||!video.videoWidth)return;
    lastTime=video.currentTime;
    const w=Math.min(video.videoWidth,640),h=Math.round(video.videoHeight*w/video.videoWidth);
    if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h}
    ctx.drawImage(video,0,0,w,h);
    try{
      segmenter.segmentForVideo(canvas,performance.now(),result=>{
        const masks=result.confidenceMasks;if(!masks||!masks.length)return;
        const mask=masks[masks.length>1?1:0].getAsFloat32Array();if(mask.length!==w*h)return;
        if(frame++%15===0){const flipped=LittleWorldsCutout.looksInverted(mask,w,h);if(flipped!==null)invert=flipped}
        const image=ctx.getImageData(0,0,w,h);LittleWorldsCutout.applyMask(image.data,mask,invert);ctx.putImageData(image,0,0);
      });
    }catch(e){console.error('Cut-out stopped:',e);cancelAnimationFrame(cutLoop);segmenterFailed=true;$('webcamCut').checked=false;applyWebcamMode()}
  };
  tick();
}
async function applyWebcamMode(){
  cancelAnimationFrame(cutLoop);
  const video=$('webcamVideo'),canvas=$('webcamCanvas'),box=$('webcamBox');
  if(!webcamStream)return;
  let cut=$('webcamCut').checked&&!segmenterFailed;
  if(cut){
    $('webcamStatus').textContent='Loading the cut-out model…';
    try{await loadSegmenter()}catch(e){console.error(e);segmenterFailed=true;cut=false;$('webcamCut').checked=false}
    if(!webcamStream)return;
  }
  video.hidden=false;video.classList.toggle('offscreen',cut);canvas.hidden=!cut;box.classList.add('live');box.classList.toggle('cut',cut);
  if(cut)runCutout();
  $('webcamStatus').textContent=cut?'Webcam preview is on and shows only you, on top of your background. It stays in this tab. In OBS, add your real webcam above the Browser Source and remove its background there.':segmenterFailed?'Could not load the cut-out model, so the plain camera is shown. Your room will show behind you.':'Webcam preview is on (plain camera, your room shows). Tick Show only me to remove it. It stays in this tab.';
}
function webcamOff(){
  webcamToken++;cancelAnimationFrame(cutLoop);if(webcamStream)webcamStream.getTracks().forEach(t=>t.stop());webcamStream=null;
  const v=$('webcamVideo');v.srcObject=null;v.hidden=true;v.classList.remove('offscreen');$('webcamCanvas').hidden=true;$('webcamBox').classList.remove('live','cut');$('webcamToggle').textContent='Turn on webcam preview'}
async function webcamOn(){
  if(!navigator.mediaDevices?.getUserMedia){$('webcamStatus').textContent='This browser cannot open a webcam on this page.';return}
  $('webcamToggle').disabled=true;$('webcamStatus').textContent='Asking your browser for the camera…';
  try{
    const mine=webcamToken,stream=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:1280},height:{ideal:720}},audio:false});
    if(mine!==webcamToken){stream.getTracks().forEach(t=>t.stop());return}
    webcamStream=stream;const v=$('webcamVideo');v.srcObject=stream;v.hidden=false;await v.play().catch(()=>{});
    if(mine!==webcamToken)return;
    $('webcamToggle').textContent='Turn off webcam preview';
    webcamStream.getVideoTracks()[0].addEventListener('ended',()=>{webcamOff();$('webcamStatus').textContent='The camera was disconnected.'});
    await applyWebcamMode();
  }catch(e){
    console.error('Webcam preview failed:',e);webcamOff();
    $('webcamStatus').textContent=e.name==='NotAllowedError'?'The browser blocked the camera. Click the camera icon in the address bar to allow it, and on a Mac check System Settings, Privacy & Security, Camera.':e.name==='NotFoundError'?'No camera was found.':e.name==='NotReadableError'?'Another app is using the camera. Close it there, or pick a different camera, then try again.':'Could not start the camera.';
  }finally{$('webcamToggle').disabled=false}
}
$('webcamToggle').addEventListener('click',()=>webcamStream?webcamOff():webcamOn());
$('webcamCut').addEventListener('change',()=>{segmenterFailed=false;applyWebcamMode()});
$('webcamFrame').addEventListener('change',()=>{scene.dataset.cam=$('webcamFrame').value});

// Streamer backgrounds: presets above, plus AI-made or uploaded full backgrounds that apply without the approval queue.
const bgSay=text=>{$('bgStatus').textContent=text};
const bgCall=(name,data)=>api(route('/background/'+name),'POST',data);
function shrinkImage(file){return new Promise((resolve,reject)=>{
  const url=URL.createObjectURL(file),img=new Image();
  img.onerror=()=>{URL.revokeObjectURL(url);reject(new Error('The browser could not read that file as an image.'))};
  img.onload=()=>{URL.revokeObjectURL(url);const k=Math.min(1,1600/img.width,900/img.height),c=document.createElement('canvas');
    c.width=Math.max(1,Math.round(img.width*k));c.height=Math.max(1,Math.round(img.height*k));c.getContext('2d').drawImage(img,0,0,c.width,c.height);
    let q=.85,out='';do{out=c.toDataURL('image/webp',q);q-=.15}while(out.length>880000&&q>.2);
    out.length>880000?reject(new Error('That image is too detailed to shrink enough. Try a smaller picture.')):resolve(out)};
  img.src=url})}
$('bgCreateOpen').addEventListener('click',()=>{$('bgCreate').hidden=!$('bgCreate').hidden;if(!$('bgCreate').hidden)$('bgPrompt').focus()});
$('bgMake').addEventListener('click',async()=>{
  const description=$('bgPrompt').value.trim();if(!description){bgSay('Describe the background you want first.');return}
  const epoch=sessionEpoch;$('bgMake').disabled=true;$('bgUse').hidden=true;bgSay('Checking and making your background… this can take up to a minute.');
  try{const result=await bgCall('create',{description,style:$('bgStyle').value});if(epoch!==sessionEpoch)return;$('bgPreview').src=result.art;$('bgPreview').hidden=false;$('bgUse').hidden=false;bgSay('Here it is. Use it, or press Create again for another version.')}
  catch(e){if(epoch===sessionEpoch)bgSay(e.message)}finally{$('bgMake').disabled=false}});
$('bgUse').addEventListener('click',async()=>{try{await bgCall('apply',{use:'preview'});bgSay('Your AI background is on.');$('bgUse').hidden=true;update(true)}catch(e){bgSay(e.message)}});
$('bgFile').addEventListener('change',async()=>{const file=$('bgFile').files[0];$('bgFile').value='';if(!file)return;bgSay('Preparing your image…');
  try{await bgCall('apply',{image:await shrinkImage(file)});bgSay('Your uploaded background is on.');update(true)}catch(e){bgSay(e.message)}});
$('bgClear').addEventListener('click',async()=>{try{await bgCall('clear',{});bgSay('Custom background removed.');update(true)}catch(e){bgSay(e.message)}});

// Leaving a room must not leave one person's private work on screen for the next person using this tab.
function resetSessionWork(){
  ctx.clearRect(0,0,canvas.width,canvas.height);
  ['creator','description','bgPrompt'].forEach(id=>{$(id).value=''});
  clearPreview();setMode(false);
  kind='object';document.querySelectorAll('.kind').forEach(x=>x.classList.toggle('active',x.dataset.kind==='object'));$('kindHelp').textContent=KIND_HELP.object;
  $('artStyle').value='neon';$('bgStyle').value='neon';
  $('previewLeft').textContent='Try as often as you like, up to 5 times. Nothing is sent until you press Send for review.';
  $('status').textContent='Your drawing stays private until approved.';
  position={x:22,y:32};marker.style.left='22%';marker.style.top='32%';
  $('bgPreview').hidden=true;$('bgPreview').removeAttribute('src');$('bgUse').hidden=true;$('bgCreate').hidden=true;
  $('bgStatus').textContent='Presets work offline. AI backgrounds need the AI art setting and cost a few cents each.';
  sizeFocus=null;library=[];libImages.clear();libLoading.clear();closeHelper(true);
}

// "From your stream": everything approved (and every background the streamer made) can be reused as a background.
// The review poll lists only metadata; each picture is fetched once, then cached, so polling stays light.
const libImages=new Map(),libLoading=new Set();
async function fetchLibraryImage(id){
  if(libLoading.has(id)||libImages.has(id))return;
  libLoading.add(id);const epoch=sessionEpoch;
  try{const result=await api(route(`/library/${id}`));if(epoch!==sessionEpoch)return;libImages.set(id,result.image);renderLibrary()}
  catch(_){}finally{libLoading.delete(id)}
}
async function libraryAction(id,action,body,done){
  const epoch=sessionEpoch;
  try{await api(route(`/library/${id}/${action}`),'POST',body);if(epoch!==sessionEpoch)return;bgSay(done);update(true)}
  catch(e){if(epoch===sessionEpoch)bgSay(e.message)}
}
function renderLibrary(){
  const grid=$('libGrid');grid.replaceChildren();$('libEmpty').hidden=library.length>0;
  library.slice().reverse().forEach(entry=>{
    const tile=document.createElement('div');tile.className='lib-tile';
    const pic=document.createElement('div');pic.className='lib-pic';
    const src=libImages.get(entry.id);
    if(src){const img=document.createElement('img');img.src=src;img.alt=`${entry.description}`;pic.append(img)}else{pic.textContent='…';fetchLibraryImage(entry.id)}
    const caption=document.createElement('p');caption.textContent=`${entry.creator||'Someone'}: ${entry.description||''}`.slice(0,70);
    const actions=document.createElement('div');actions.className='lib-actions';
    const full=document.createElement('button');full.type='button';full.textContent='🖼 Background';full.title='Use as the full background';
    full.addEventListener('click',()=>libraryAction(entry.id,'use',{as:'full'},'Now your full background.'));
    const piece=document.createElement('button');piece.type='button';piece.textContent='🏙 Piece';piece.title='Add as a background piece you can move and resize';
    piece.addEventListener('click',()=>libraryAction(entry.id,'use',{as:'piece'},'Added as a background piece. Drag or resize it in the scene.'));
    const del=document.createElement('button');del.type='button';del.className='lib-del';del.textContent='✕';del.title='Remove from this list';del.setAttribute('aria-label','Remove from library');
    del.addEventListener('click',()=>{libImages.delete(entry.id);libraryAction(entry.id,'delete',{},'Removed from your library.')});
    actions.append(full,piece,del);tile.append(pic,caption,actions);grid.append(tile);
  });
}

// Prompt helper: a few simple questions that write a good prompt for people who do not know how to prompt.
const Prompts=typeof LittleWorldsPrompts!=='undefined'?LittleWorldsPrompts:null,helper={target:'',placement:'object',mood:'',color:''};
function chipButtons(box,items,onPick,isOn){
  box.replaceChildren();
  items.forEach(item=>{
    const b=document.createElement('button');b.type='button';b.className='chip';b.textContent=item.label;
    b.setAttribute('aria-pressed',String(isOn(item)));b.addEventListener('click',()=>onPick(item));box.append(b);
  });
}
function helperWrite(){
  const text=Prompts.compose({idea:$('helperIdea').value,mood:helper.mood,color:helper.color,details:$('helperDetails').value});
  $('helperResult').value=text;helperCount();
}
function helperCount(){const n=$('helperResult').value.trim().length;$('helperCount').textContent=n?`${n} of ${Prompts.MAX} characters`:'Type an idea in step 1 to see your prompt.';$('helperUse').disabled=!n}
function helperRender(){
  chipButtons($('helperIdeas'),(Prompts.IDEAS[helper.placement]||Prompts.IDEAS.object).slice(0,4).map(t=>({id:t,label:t})),item=>{$('helperIdea').value=item.id;helperWrite()},()=>false);
  chipButtons($('helperMoods'),Prompts.MOODS,item=>{helper.mood=helper.mood===item.id?'':item.id;helperRender();helperWrite()},item=>helper.mood===item.id);
  chipButtons($('helperColors'),Prompts.COLORS,item=>{helper.color=helper.color===item.id?'':item.id;helperRender();helperWrite()},item=>helper.color===item.id);
  chipButtons($('helperDetailChips'),Prompts.DETAILS.map(t=>({id:t,label:t})),item=>{$('helperDetails').value=item.id;helperWrite()},()=>false);
}
function openHelper(inputId,placement){
  helper.target=inputId;helper.placement=placement;helper.mood=helper.color='';
  $('helperIdea').value=Prompts.clean($(inputId).value);$('helperDetails').value='';
  helperRender();helperWrite();$('helperOverlay').hidden=false;$('helperIdea').focus();
}
function closeHelper(reset){
  if(!Prompts)return;
  $('helperOverlay').hidden=true;
  if(reset){['helperIdea','helperDetails','helperResult'].forEach(id=>{$(id).value=''});helper.mood=helper.color='';helper.target='';helperCount()}
}
if(!Prompts){['promptHelp','bgPromptHelp'].forEach(id=>{$(id).hidden=true})}else{
$('promptHelp').addEventListener('click',()=>openHelper('description',kind));
$('bgPromptHelp').addEventListener('click',()=>openHelper('bgPrompt','full'));
$('helperClose').addEventListener('click',()=>closeHelper(false));
$('helperOverlay').addEventListener('click',e=>{if(e.target===$('helperOverlay'))closeHelper(false)});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('helperOverlay').hidden)closeHelper(false)});
$('helperIdea').addEventListener('input',helperWrite);$('helperDetails').addEventListener('input',helperWrite);$('helperResult').addEventListener('input',helperCount);
$('helperSurprise').addEventListener('click',()=>{const s=Prompts.suggest(helper.placement);$('helperIdea').value=s.idea;helper.mood=s.mood;helper.color=s.color;$('helperDetails').value='';helperRender();helperWrite()});
$('helperUse').addEventListener('click',()=>{
  const text=$('helperResult').value.trim().slice(0,Prompts.MAX),input=$(helper.target);if(!text||!input)return;
  input.value=text;input.dispatchEvent(new Event('input',{bubbles:true}));closeHelper(true);input.focus();
});
}
