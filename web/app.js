"use strict";
const $=s=>document.querySelector(s), state={mode:"recolor",ai:false,image:null,paint:false,erase:false,jobs:[],key:sessionStorage.getItem("imageforge-key")||""};
const img=$("#sourceCanvas"),mask=$("#maskCanvas"),ic=img.getContext("2d"),mc=mask.getContext("2d",{willReadFrequently:true});
let url=null;
function notice(message){const el=$("#toast");el.textContent=message;el.hidden=false;clearTimeout(window.toastTime);window.toastTime=setTimeout(()=>el.hidden=true,6500);}
async function api(path,opts={}){
  const headers=new Headers(opts.headers||{});
  if(state.key)headers.set("X-App-Key",state.key);
  const response=await fetch(path,{...opts,headers});
  if(!response.ok){let detail="HTTP "+response.status;try{detail=(await response.json()).detail||detail;}catch{}throw Error(typeof detail==="string"?detail:JSON.stringify(detail));}
  return response;
}
function mode(value){
  state.mode=value;
  const ai=["generate","edit","pose"].includes(value),select=["edit","recolor","fill","erase"].includes(value);
  document.querySelectorAll("[data-mode]").forEach(b=>{const active=b.dataset.mode===value;b.classList.toggle("active",active);b.setAttribute("aria-pressed",String(active));});
  $("#uploadGroup").hidden=value==="generate";$("#selectionGroup").hidden=!select;
  $("#promptGroup").hidden=!ai;$("#colorGroup").hidden=!["recolor","fill"].includes(value);$("#advanced").hidden=!ai;
  $("#modeHelp").textContent={
    generate:"Real text-to-image requires a separate NVIDIA GPU. Codespaces CPU cannot generate AI images.",
    edit:"AI inpainting updates selected pixels only. Areas outside your mask remain unchanged.",
    pose:"Experimental image-to-image only; exact pose control and face identity are not guaranteed.",
    recolor:"Brush tint colors ONLY painted strokes, not a complete dress. For a full dress replacement, a real GPU image-inpainting model is needed.",
    fill:"Replace only selected pixels with a solid color using the CPU.",
    erase:"Make only selected pixels transparent. This does not rebuild the hidden background."
  }[value];
  $("#submitHint").textContent=ai?"AI model is disabled without a CUDA GPU; no simulated results.":"CPU mode works without GPU or paid services.";
  $("#submitText").textContent=ai?"Generate with AI":value==="recolor"?"Apply brush tint":value==="fill"?"Apply solid fill":"Erase selected pixels";
  $("#submit").disabled=ai&&!state.ai;
}
function fit(){
  if(!state.image)return;
  const w=$("#canvasWrap");w.style.width="100%";
  const display=Math.min(w.parentElement.clientWidth,390*img.width/img.height);
  w.style.width=display+"px";w.style.height=(display*img.height/img.width)+"px";
  for(const c of [img,mask]){c.style.width="100%";c.style.height="100%";c.style.maxHeight="none";}
}
async function load(file){
  if(!file)return;
  if(file.size>12*1024*1024)throw Error("Upload must be under 12MB.");
  if(!["image/png","image/jpeg","image/webp"].includes(file.type))throw Error("Use PNG, JPG or WebP.");
  const bitmap=await createImageBitmap(file);
  if(bitmap.width*bitmap.height>16000000){bitmap.close();throw Error("Maximum image size is 16 megapixels.");}
  img.width=mask.width=bitmap.width;img.height=mask.height=bitmap.height;
  ic.drawImage(bitmap,0,0);bitmap.close();mc.clearRect(0,0,mask.width,mask.height);
  state.image=file;$("#canvasPlaceholder").hidden=true;fit();
}
function point(e){
  const r=mask.getBoundingClientRect();
  return {x:(e.clientX-r.left)*mask.width/r.width,y:(e.clientY-r.top)*mask.height/r.height};
}
function stroke(e,start=false){
  const p=point(e),width=Number($("#brushSize").value)*mask.width/Math.max(1,mask.clientWidth);
  mc.save();mc.globalCompositeOperation=state.erase?"destination-out":"source-over";
  mc.lineWidth=width;mc.lineCap="round";mc.lineJoin="round";mc.strokeStyle=mc.fillStyle="#cba0ff";
  if(start){mc.beginPath();mc.arc(p.x,p.y,width/2,0,Math.PI*2);mc.fill();}
  else{mc.lineTo(p.x,p.y);mc.stroke();}
  mc.restore();mc.beginPath();mc.moveTo(p.x,p.y);
}
async function selection(){
  const image=mc.getImageData(0,0,mask.width,mask.height),bytes=image.data;
  let selected=0;
  for(let i=0;i<bytes.length;i+=4){const value=bytes[i+3]>=128?255:0;selected+=value;bytes[i]=bytes[i+1]=bytes[i+2]=value;bytes[i+3]=255;}
  if(!selected)throw Error("Paint a selection first.");
  const canvas=document.createElement("canvas");canvas.width=mask.width;canvas.height=mask.height;
  canvas.getContext("2d").putImageData(image,0,0);
  return new Promise((resolve,reject)=>canvas.toBlob(b=>b?resolve(b):reject(Error("Mask export failed")),"image/png"));
}
async function autoMask(target,button){
  if(!state.image)return notice("Upload an image first.");
  button.disabled=true;
  try{
    const form=new FormData();form.set("target",target);form.set("image",state.image);
    const bitmap=await createImageBitmap(await(await api("/api/mask",{method:"POST",body:form})).blob());
    const c=document.createElement("canvas");c.width=mask.width;c.height=mask.height;
    const context=c.getContext("2d",{willReadFrequently:true});context.drawImage(bitmap,0,0,c.width,c.height);bitmap.close();
    const data=context.getImageData(0,0,c.width,c.height);
    for(let i=0;i<data.data.length;i+=4){const v=data.data[i];data.data[i]=203;data.data[i+1]=160;data.data[i+2]=255;data.data[i+3]=v>=128?255:0;}
    mc.putImageData(data,0,0);notice("Mask suggestion ready; inspect it before editing.");
  }catch(e){notice(e.message);}finally{button.disabled=false;}
}
function button(label,fn){const b=document.createElement("button");b.type="button";b.className="secondary";b.textContent=label;b.onclick=fn;return b;}
async function refresh(){
  try{state.jobs=await(await api("/api/jobs")).json();render();}
  catch(e){$("#jobs").textContent=e.message;}
}
function render(){
  const root=$("#jobs");root.replaceChildren();
  if(!state.jobs.length){const el=document.createElement("p");el.className="empty";el.textContent="Nothing here yet. Create your first image edit.";root.append(el);}
  for(const job of state.jobs){
    const card=document.createElement("article");card.className="job";
    const row=document.createElement("div");row.className="job-head";
    const type=document.createElement("span");type.textContent=job.mode;
    const status=document.createElement("span");status.textContent=job.status;status.className="status "+job.status;
    row.append(type,status);
    const title=document.createElement("h3");title.textContent=job.prompt||"Selected image edit";card.append(row,title);
    if(job.error){const p=document.createElement("p");p.className="error";p.textContent=job.error;card.append(p);}
    const actions=document.createElement("div");actions.className="job-actions";
    if(job.status==="ready")actions.append(button("Preview",()=>preview(job.id)),button("Download",()=>download(job.id)));
    if(!["queued","running"].includes(job.status))actions.append(button("Delete",()=>remove(job.id)));
    card.append(actions);root.append(card);
  }
}
async function blob(id){return(await api("/api/jobs/"+id+"/image")).blob();}
async function preview(id){
  try{if(url)URL.revokeObjectURL(url);url=URL.createObjectURL(await blob(id));$("#previewImage").src=url;$("#downloadPreview").onclick=()=>download(id);$("#previewDialog").showModal();}
  catch(e){notice(e.message);}
}
async function download(id){
  try{const objectURL=URL.createObjectURL(await blob(id)),a=document.createElement("a");a.href=objectURL;a.download="imageforge-"+id.slice(0,8)+".png";document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(objectURL),60000);}
  catch(e){notice(e.message);}
}
async function remove(id){
  if(!confirm("Permanently delete this image?"))return;
  try{await api("/api/jobs/"+id,{method:"DELETE"});await refresh();}catch(e){notice(e.message);}
}
$("#jobForm").addEventListener("submit",async e=>{
  e.preventDefault();
  const chosen=state.mode,form=new FormData(),submit=$("#submit");
  for(const id of ["prompt","negative","seed","steps","strength","width","height","color"])form.set(id,$("#"+id).value);
  form.set("mode",chosen);
  if(chosen!=="generate"){
    if(!state.image)return notice("Upload an image first.");
    form.set("image",state.image,state.image.name);
    if(["edit","recolor","fill","erase"].includes(chosen)){
      try{form.set("mask",await selection(),"mask.png");}catch(err){return notice(err.message);}
    }
  }
  submit.disabled=true;
  try{await api("/api/jobs",{method:"POST",body:form});notice("Job queued. Check your library.");await refresh();location.hash="library";}
  catch(err){notice(err.message);}
  finally{submit.disabled=["generate","edit","pose"].includes(chosen)&&!state.ai;}
});
$("#upload").addEventListener("change",async e=>{
  try{await load(e.target.files[0]);}catch(err){state.image=null;$("#canvasPlaceholder").hidden=false;notice(err.message);}
});
mask.addEventListener("pointerdown",e=>{if(!state.image)return;e.preventDefault();state.paint=true;mask.setPointerCapture(e.pointerId);stroke(e,true);});
mask.addEventListener("pointermove",e=>{if(state.paint)stroke(e);});
for(const name of ["pointerup","pointercancel","lostpointercapture"])mask.addEventListener(name,()=>state.paint=false);
$("#brushBtn").onclick=()=>{state.erase=false;$("#brushBtn").classList.add("active");$("#eraserBtn").classList.remove("active");};
$("#eraserBtn").onclick=()=>{state.erase=true;$("#eraserBtn").classList.add("active");$("#brushBtn").classList.remove("active");};
$("#clearMask").onclick=()=>mc.clearRect(0,0,mask.width,mask.height);
$("#brushSize").oninput=()=>{$("#brushValue").textContent=$("#brushSize").value;};
$("#exportMask").onclick=async()=>{
  try{
    const file=await selection();
    const url=URL.createObjectURL(file);
    const a=document.createElement("a");
    a.href=url;a.download="imageforge-mask.png";document.body.append(a);a.click();a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),60000);
    notice("Mask downloaded: white means edit, black means protect.");
  }catch(e){notice(e.message);}
};
document.querySelectorAll("[data-select]").forEach(b=>b.onclick=()=>autoMask(b.dataset.select,b));
document.querySelectorAll("[data-mode]").forEach(b=>b.onclick=()=>mode(b.dataset.mode));
$("#refresh").onclick=refresh;
$("#saveKey").onclick=()=>{state.key=$("#accessKey").value.trim();if(state.key)sessionStorage.setItem("imageforge-key",state.key);else sessionStorage.removeItem("imageforge-key");refresh();};
$("#closePreview").onclick=()=>{if(url)URL.revokeObjectURL(url);url=null;$("#previewDialog").close();$("#previewImage").removeAttribute("src");};
window.addEventListener("resize",fit);
async function init(){
  $("#accessKey").value=state.key;
  try{const info=await(await api("/api/status")).json();state.ai=info.ai_configured;$("#engineLabel").textContent=state.ai?"AI adapter enabled":"CPU editor ready";}
  catch(e){$("#engineLabel").textContent="Server offline";notice(e.message);}
  mode(state.mode);await refresh();
}
init();
setInterval(()=>{if(!document.hidden&&state.jobs.some(j=>["queued","running"].includes(j.status)))refresh();},3000);
