'use strict';
const menuButton=document.querySelector('.menu-toggle');
const scrim=document.querySelector('.nav-scrim');
function closeNavigation(){document.body.classList.remove('nav-open');menuButton?.setAttribute('aria-expanded','false');}
menuButton?.addEventListener('click',()=>{const open=document.body.classList.toggle('nav-open');menuButton.setAttribute('aria-expanded',String(open));if(open)document.querySelector('.side-nav a')?.focus();});
scrim?.addEventListener('click',closeNavigation);
document.addEventListener('keydown',event=>{if(event.key==='Escape'){closeNavigation();menuButton?.focus();}if(event.key==='/'&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)&&!document.activeElement.isContentEditable){const search=document.querySelector('.global-search input');if(search){event.preventDefault();search.focus();}}});
document.querySelectorAll('table.table').forEach(table=>{const headings=[...table.querySelectorAll('thead th')].map(cell=>cell.textContent.trim());table.querySelectorAll('tbody tr').forEach(row=>[...row.cells].forEach((cell,index)=>{if(!cell.dataset.label)cell.dataset.label=headings[index]||'';}));});
document.querySelectorAll('form').forEach(form=>{form.addEventListener('submit',event=>{if(form.method.toLowerCase()!=='post')return;if(form.dataset.submitting==='true'){event.preventDefault();return;}form.dataset.submitting='true';const button=event.submitter;if(button){button.setAttribute('aria-busy','true');setTimeout(()=>{button.disabled=true;},0);}setTimeout(()=>{delete form.dataset.submitting;if(button){button.disabled=false;button.removeAttribute('aria-busy');}},10000);});});
window.addEventListener('pageshow',()=>{document.querySelectorAll('form').forEach(form=>{delete form.dataset.submitting;form.querySelectorAll('[aria-busy=true]').forEach(button=>{button.disabled=false;button.removeAttribute('aria-busy');});});});

// As preferências visuais ficam apenas neste navegador.
const themeToggle=document.querySelector('[data-theme-toggle]');
function reflectTheme(){
  const dark=document.documentElement.dataset.theme!=='light';
  const label=dark?'Ativar tema claro':'Ativar tema escuro';
  if(themeToggle){themeToggle.setAttribute('aria-label',label);themeToggle.title=label;themeToggle.querySelector('.theme-label').textContent=dark?'Tema claro':'Tema escuro';}
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content',dark?'#091526':'#eff3fa');
}
reflectTheme();
themeToggle?.addEventListener('click',()=>{
  const theme=document.documentElement.dataset.theme==='light'?'dark':'light';
  document.documentElement.dataset.theme=theme;
  try{localStorage.setItem('solutec-theme',theme);}catch(e){}
  reflectTheme();
});
const equipmentResults=document.querySelector('[data-equipment-view]');
const viewButtons=document.querySelectorAll('[data-view-button]');
function setEquipmentView(view){
  if(!equipmentResults)return;
  equipmentResults.dataset.equipmentView=view;
  viewButtons.forEach(button=>{const active=button.dataset.viewButton===view;button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));});
}
if(equipmentResults){
  try{const preferred=localStorage.getItem('solutec-inventory-view');if(preferred==='cards'||preferred==='list')setEquipmentView(preferred);}catch(e){}
  viewButtons.forEach(button=>button.addEventListener('click',()=>{const view=button.dataset.viewButton;setEquipmentView(view);try{localStorage.setItem('solutec-inventory-view',view);}catch(e){}}));
}
