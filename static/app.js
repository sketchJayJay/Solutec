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
