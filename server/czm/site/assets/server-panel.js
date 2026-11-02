(() => {
  'use strict';
  const $ = id => document.getElementById(id), prefix = '/api/v1/server-panel';
  const state = {csrf: '', address: '', tab: 'overview', path: '', entries: [], edit: null, original: '', loading: false, upload: false, cpu: [], ram: [], generation: 0};
  const errors = {session:'Войдите в панель заново.',forbidden:'Этому аккаунту доступ к серверу не выдан.',credentials:'Проверьте логин и пароль.',slow:'Слишком много попыток. Подождите и повторите.',origin:'Откройте панель на counter-zombie.ru.',csrf:'Обновите страницу и повторите действие.',missing:'Файл или папка не найдены.',path:'Недопустимый путь или имя.',protected:'Этот файл или параметр защищён.',conflict:'Документ уже изменился. Откройте его заново, чтобы не перезаписать новые изменения.',large:'Файл слишком большой.',encoding:'Проверьте кодировку. Для новых символов выберите UTF-8.',filesystem:'Не удалось выполнить операцию с файлом. Проверьте имя, доступ и свободное место.',agent_unavailable:'Нет связи с управлением сервером. Повторите позже.',game_unavailable:'Сервер не отвечает. Проверьте состояние и повторите.',auth_unavailable:'Вход временно недоступен. Повторите позже.',use_editor:'Этот документ изменяется только через редактор.',disk_full:'На сервере недостаточно свободного места.',request:'Проверьте заполненные поля.',binary:'Этот файл нельзя открыть в текстовом редакторе.',revision:'Обновите папку или документ.',code:'Неверный или просроченный код.',email:'Проверьте почту аккаунта.'};
  let toastTimer, mode = 'password', confirmResolve, nameResolve, listGeneration = 0;
  function toast(text, error=false) { const active=[...document.querySelectorAll('dialog[open]')].at(-1); (active||document.body).append($('toast')); clearTimeout(toastTimer); $('toast').textContent=text; $('toast').classList.toggle('error',error); $('toast').hidden=false; toastTimer=setTimeout(()=>{$('toast').hidden=true;},6000); }
  function message(error) { return errors[error.code] || error.message || 'Не удалось выполнить действие.'; }
  function report(error) { toast(message(error),true); }
  async function api(route, options={}) {
    const headers = {'X-CZM-CSRF':state.csrf, ...options.headers};
    if (options.json !== undefined) {headers['Content-Type']='application/json'; options.body=JSON.stringify(options.json); delete options.json;}
    let response;
    try {response=await fetch(prefix+route,{...options,headers,credentials:'same-origin',cache:'no-store'});} catch (_) {throw new Error('Не удалось связаться с сайтом. Проверьте интернет.');}
    const data=await response.json();
    if (!response.ok) {
      if (response.status===401 && route!=='/login' && route!=='/session') showLogin();
      const error=new Error(errors[data.error] || 'Не удалось выполнить действие.'); error.code=data.error; throw error;
    }
    return data;
  }
  const query = path => '?'+new URLSearchParams({path});
  function bytes(n) {if(!Number.isFinite(n))return '—'; if(n<1024)return n+' B'; if(n<1048576)return (n/1024).toFixed(1)+' KiB'; if(n<1073741824)return (n/1048576).toFixed(1)+' MiB'; return (n/1073741824).toFixed(2)+' GiB';}
  function date(n) {return new Date(n*1000).toLocaleString('ru-RU',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});}
  function uptime(n) {if(!n)return '—'; const d=Math.floor(n/86400),h=Math.floor(n%86400/3600),m=Math.floor(n%3600/60);return (d?d+' д ':'')+(h?h+' ч ':'')+m+' мин';}
  function node(tag, cls, text) {const e=document.createElement(tag); if(cls)e.className=cls; if(text!==undefined)e.textContent=text; return e;}
  function confirm(title,text,yes='Подтвердить') {return new Promise(resolve=>{confirmResolve=resolve;$('confirm-title').textContent=title;$('confirm-text').textContent=text;$('confirm-yes').textContent=yes;$('confirm').showModal();});}
  function resolveConfirm(value) {$('confirm').close(); if(confirmResolve)confirmResolve(value); confirmResolve=null;}
  $('confirm-yes').addEventListener('click',()=>resolveConfirm(true));$('confirm-no').addEventListener('click',()=>resolveConfirm(false));$('confirm').addEventListener('cancel',e=>{e.preventDefault();resolveConfirm(false);});
  function askName(title,placeholder) {return new Promise(resolve=>{nameResolve=resolve;$('name-title').textContent=title;$('name-input').value='';$('name-input').placeholder=placeholder;$('name-dialog').showModal();$('name-input').focus();});}
  function resolveName(value) {$('name-dialog').close(); if(nameResolve)nameResolve(value); nameResolve=null;}
  $('name-cancel').addEventListener('click',()=>resolveName(null));$('name-dialog').addEventListener('cancel',e=>{e.preventDefault();resolveName(null);});$('name-form').addEventListener('submit',e=>{e.preventDefault();resolveName($('name-input').value.trim());});
  function dirty() {return state.edit && ($('editor-text').value!==state.original || $('editor-encoding').value!==state.edit.encoding);}
  async function closeEditor() {if(dirty()&&!await confirm('Закрыть без сохранения?','В документе есть несохранённые изменения.','Закрыть'))return; $('editor').close();state.edit=null;}
  $('editor-close').addEventListener('click',closeEditor);$('editor').addEventListener('cancel',e=>{e.preventDefault();closeEditor();});
  window.addEventListener('beforeunload',e=>{if(dirty()||state.upload){e.preventDefault();e.returnValue='';}});
  function showLogin() {state.generation++;state.csrf='';$('signin').hidden=false;$('workspace').hidden=true;$('logout').hidden=true;if($('editor').open)$('editor').close();state.edit=null;}
  async function loadSession() {
    const session=await api('/session');state.csrf=session.csrf;state.address=session.address;
    $('owner-name').textContent=session.profile.nick;$('server-address').textContent=state.address;
    $('signin').hidden=true;$('workspace').hidden=false;$('logout').hidden=false;await refreshStatus();
  }
  $('login-form').addEventListener('submit',async e=>{
    e.preventDefault();const button=$('login-submit');button.disabled=true;$('login-error').hidden=true;
    try {const result=await api('/login',{method:'POST',json:{nick:$('login-name').value,password:$('login-password').value}});
      $('login-password').value='';await loadSession();
    } catch(error){$('login-error').textContent=message(error);$('login-error').hidden=false;} finally {button.disabled=false;}
  });
  $('logout').addEventListener('click',async()=>{if(dirty()&&!await confirm('Выйти из панели?','Несохранённые изменения документа будут потеряны.','Выйти'))return;try{await api('/logout',{method:'POST'});showLogin();}catch(error){report(error);}});
  async function switchTab(tab) {
    if(!['overview','console','files','settings'].includes(tab))return;
    state.tab=tab;document.querySelectorAll('.panel-nav [data-tab]').forEach(e=>e.classList.toggle('active',e.dataset.tab===tab));document.querySelectorAll('.tab-panel').forEach(e=>{e.hidden=e.id!=='tab-'+tab;});
    $('page-title').textContent={overview:'Обзор сервера',console:'Консоль сервера',files:'Файлы сервера',settings:'Настройки сервера'}[tab];
    if(tab==='files')await listFiles(state.path);if(tab==='console')await loadConsole();
  }
  document.querySelectorAll('[data-tab]').forEach(e=>e.addEventListener('click',()=>switchTab(e.dataset.tab).catch(report)));
  function spark(id,values,max) {const path=$(id).querySelector('path');path.setAttribute('d',values.map((n,i)=>(i?'L':'M')+(i*240/Math.max(1,values.length-1)).toFixed(1)+','+(34-Math.min(1,n/Math.max(1,max))*30).toFixed(1)).join(' '));}
  async function refreshStatus() {
    if(!state.csrf||state.loading)return;state.loading=true;const generation=state.generation;
    try {
      const info=await api('/status');if(generation!==state.generation)return;
      const online=info.state==='active', names={active:'Работает',inactive:'Остановлен',failed:'Ошибка запуска',activating:'Запускается',deactivating:'Останавливается'};
      const label=names[info.state]||'Нет данных';$('status-pill').querySelector('b').textContent=label;$('status-pill').classList.toggle('online',online);$('sidebar-status').textContent=label;$('sidebar-dot').classList.toggle('online',online);
      $('sync-state').textContent='Обновлено '+new Date(info.observed_at*1000).toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit',second:'2-digit'});$('sync-state').classList.remove('error');
      const game=info.game;$('server-name').textContent=game?.name||'CZM Zombie Server';$('server-map').textContent=game?.map||'—';$('server-players').textContent=game?`${game.players} / ${game.slots}`:'—';$('server-uptime').textContent=uptime(info.uptime);
      $('cpu-value').textContent=info.cpu.toFixed(1)+'%';$('cpu-limit').textContent='из '+info.cpu_limit+'%';$('cpu-bar').style.width=Math.min(100,info.cpu/info.cpu_limit*100)+'%';
      $('ram-value').textContent=bytes(info.memory);$('ram-limit').textContent='из '+bytes(info.memory_limit);$('ram-bar').style.width=Math.min(100,info.memory/info.memory_limit*100)+'%';$('disk-value').textContent=bytes(info.disk);$('players-value').textContent=game?`${game.players} / ${game.slots}`:'—';$('bots-note').textContent=game?`${game.bots} ботов · карта ${game.map}`:'Игровой сервер не отвечает';
      document.querySelectorAll('.players-decoration i').forEach((e,i)=>e.classList.toggle('on',!!game&&i<Math.ceil(game.players/Math.max(1,game.slots)*8)));
      state.cpu.push(info.cpu);state.ram.push(info.memory);if(state.cpu.length>30){state.cpu.shift();state.ram.shift();}spark('cpu-spark',state.cpu,info.cpu_limit);spark('ram-spark',state.ram,info.memory_limit);
      document.querySelectorAll('[data-power]').forEach(e=>{e.disabled=(e.dataset.power==='start'&&online)||(e.dataset.power==='stop'&&info.state==='inactive');});
    } catch(error){$('sync-state').textContent='Нет связи · данные устарели';$('sync-state').classList.add('error');document.querySelectorAll('[data-power]').forEach(e=>{e.disabled=true;});} finally {state.loading=false;}
  }
  document.querySelectorAll('[data-power]').forEach(button=>button.addEventListener('click',async()=>{
    const action=button.dataset.power;if(action!=='start'&&!await confirm(action==='stop'?'Остановить сервер?':'Перезапустить сервер?','Подключённые игроки будут отключены.',action==='stop'?'Остановить':'Перезапустить'))return;
    document.querySelectorAll('[data-power]').forEach(e=>{e.disabled=true;});
    try {await api('/power',{method:'POST',json:{action}});toast('Действие выполнено. Обновляем состояние…');await refreshStatus();}catch(error){report(error);await refreshStatus();}
  }));
  $('copy-address').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(state.address);toast('Адрес сервера скопирован.');}catch(_){toast('Адрес сервера: '+state.address);}});
  async function loadConsole(){try{const data=await api('/console');$('console-output').textContent=data.text||'Журнал пока пуст.';$('console-output').scrollTop=$('console-output').scrollHeight;}catch(error){$('console-output').textContent=message(error);}}
  $('refresh-console').addEventListener('click',loadConsole);
  $('console-form').addEventListener('submit',async e=>{e.preventDefault();const input=$('console-command'),command=input.value.trim();if(!command)return;input.disabled=true;try{const result=await api('/console',{method:'POST',json:{command}});$('console-output').textContent=($('console-output').textContent+'\n› '+command+'\n'+result.text).slice(-48000);$('console-output').scrollTop=$('console-output').scrollHeight;input.value='';}catch(error){report(error);}finally{input.disabled=false;input.focus();}});
  async function listFiles(path='') {
    const generation=++listGeneration;$('file-list').replaceChildren(node('div','empty-folder','Загрузка папки…'));
    const data=await api('/files'+query(path));if(generation!==listGeneration)return;
    state.path=path;state.entries=data.entries;$('file-search').value='';renderFiles();renderCrumbs();
  }
  function renderCrumbs(){const root=$('breadcrumbs');root.replaceChildren();const home=node('button','','⌂ Сервер');home.type='button';home.addEventListener('click',()=>listFiles('').catch(report));root.append(home);let path='';for(const part of state.path.split('/').filter(Boolean)){path+=(path?'/':'')+part;const target=path,button=node('button','',part);button.type='button';button.addEventListener('click',()=>listFiles(target).catch(report));root.append(node('span','','/'),button);}}
  function renderFiles() {
    const search=$('file-search').value.toLocaleLowerCase(),list=$('file-list');list.replaceChildren();const entries=state.entries.filter(e=>e.name.toLocaleLowerCase().includes(search));$('file-count').textContent=entries.length+' объектов';
    if(!entries.length){list.append(node('div','empty-folder',search?'Ничего не найдено.':'Папка пока пустая.'));return;}
    for(const entry of entries){const row=node('div','file-row'+(entry.directory?' folder':'')),name=node('button','file-name');name.type='button';name.append(node('span','file-icon',entry.directory?'▱':'▤'),node('span','',entry.name));name.addEventListener('click',()=>{if(entry.directory)listFiles(entry.path).catch(report);else if(entry.editable)openEditor(entry.path).catch(report);else download(entry.path);});row.append(name,node('span','',entry.directory?'—':bytes(entry.size)),node('span','file-date',date(entry.modified)));const actions=node('div','file-actions');
      if(!entry.directory){if(entry.editable){const edit=node('button','','✎');edit.title='Редактировать';edit.setAttribute('aria-label','Редактировать '+entry.name);edit.addEventListener('click',()=>openEditor(entry.path).catch(report));actions.append(edit);}if(entry.path!=='server.cfg'){const down=node('button','','↓');down.title='Скачать';down.setAttribute('aria-label','Скачать '+entry.name);down.addEventListener('click',()=>download(entry.path));actions.append(down);}const del=node('button','','×');del.title='Удалить';del.setAttribute('aria-label','Удалить '+entry.name);del.addEventListener('click',()=>deleteFile(entry).catch(report));actions.append(del);}row.append(actions);list.append(row);}
  }
  $('file-search').addEventListener('input',renderFiles);
  function download(path){const a=node('a');a.href=prefix+'/download'+query(path);a.download=path.split('/').pop();document.body.append(a);a.click();a.remove();}
  async function deleteFile(entry){if(!await confirm('Удалить файл?',entry.path+' — файл будет удалён с сервера и из загрузки ресурсов.','Удалить'))return;const meta=await api('/metadata'+query(entry.path));await api('/file'+query(entry.path),{method:'DELETE',headers:{'If-Match':meta.revision}});toast('Файл удалён.');await listFiles(state.path);}
  async function openEditor(path) {
    if(dirty()&&!await confirm('Открыть другой документ?','Текущие изменения не сохранены.','Открыть'))return;
    const edit=await api('/file'+query(path));state.edit=edit;state.original=edit.text;$('editor-name').textContent=path.split('/').pop();$('editor-path').textContent=path;$('editor-text').value=edit.text;$('editor-encoding').value=edit.encoding;$('protected-note').hidden=!edit.protected;editorChanged();if(!$('editor').open)$('editor').showModal();await loadHistory(path);
  }
  document.querySelectorAll('[data-open]').forEach(button=>button.addEventListener('click',()=>openEditor(button.dataset.open).catch(report)));
  function editorChanged(){$('editor-state').textContent=dirty()?'Есть несохранённые изменения':'Все изменения сохранены';$('editor-state').classList.toggle('dirty',!!dirty());$('editor-lines').textContent=$('editor-text').value.split('\n').length+' строк';}
  $('editor-text').addEventListener('input',editorChanged);$('editor-encoding').addEventListener('change',editorChanged);
  $('editor-text').addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'){e.preventDefault();$('editor-save').click();}if(e.key==='Tab'){e.preventDefault();const a=e.target.selectionStart,b=e.target.selectionEnd;e.target.setRangeText('    ',a,b,'end');editorChanged();}});
  $('editor-save').addEventListener('click',async()=>{if(!state.edit)return;const button=$('editor-save');button.disabled=true;try{const result=await api('/file',{method:'POST',json:{path:state.edit.path,text:$('editor-text').value,revision:state.edit.revision,encoding:$('editor-encoding').value}});state.edit.revision=result.revision;state.edit.encoding=$('editor-encoding').value;state.original=$('editor-text').value;editorChanged();toast('Документ сохранён. Резервная копия создана.');await loadHistory(state.edit.path);if(!result.fastdl_synced)toast('Документ сохранён, но загрузку ресурсов нужно проверить.',true);}catch(error){report(error);}finally{button.disabled=false;}});
  async function loadHistory(path){const root=$('history-list');root.replaceChildren();const history=await api('/history'+query(path));for(const entry of history.entries){const row=node('div','history-row');row.append(node('span','',date(entry.created)+' · '+bytes(entry.size)));const button=node('button','','Восстановить');button.addEventListener('click',async()=>{if(!await confirm('Восстановить копию?',`Будет восстановлена версия ${date(entry.created)}. Текущий документ сначала сохранится в резервной копии.`,'Восстановить'))return;try{await api('/restore',{method:'POST',json:{path,revision:state.edit.revision,backup:entry.id}});state.original=$('editor-text').value;state.edit=null;await openEditor(path);toast('Копия восстановлена.');}catch(error){report(error);}});row.append(button);root.append(row);}if(!history.entries.length)root.append(node('p','footnote','Копии появятся после первого изменения документа. Хранятся 10 последних версий.'));}
  $('new-folder').addEventListener('click',async()=>{try{const name=await askName('Новая папка','Название папки');if(!name)return;await api('/directory',{method:'POST',json:{path:(state.path?state.path+'/':'')+name}});await listFiles(state.path);toast('Папка создана.');}catch(error){report(error);}});
  $('new-file').addEventListener('click',async()=>{try{const name=await askName('Новый документ','Например custom.cfg');if(!name)return;const path=(state.path?state.path+'/':'')+name;await api('/file',{method:'POST',json:{path,text:'',revision:'new',encoding:'utf-8'}});await listFiles(state.path);await openEditor(path);}catch(error){report(error);}});
  function sendUpload(file,path,revision){return new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest();xhr.open('PUT',prefix+'/upload'+query(path));xhr.setRequestHeader('X-CZM-CSRF',state.csrf);xhr.setRequestHeader('If-Match',revision);xhr.setRequestHeader('Content-Type','application/octet-stream');xhr.timeout=180000;xhr.upload.onprogress=e=>{if(e.lengthComputable)$('upload-meter').value=e.loaded/e.total*100;};xhr.onload=()=>{let data;try{data=JSON.parse(xhr.responseText);}catch(_){reject(new Error('Не удалось завершить загрузку.'));return;}if(xhr.status>=200&&xhr.status<300)resolve(data);else{const error=new Error(errors[data.error]||'Не удалось загрузить файл.');error.code=data.error;reject(error);}};xhr.onerror=()=>reject(new Error('Соединение прервано. Файл не загружен.'));xhr.ontimeout=()=>reject(new Error('Время загрузки истекло. Попробуйте ещё раз.'));xhr.send(file);});}
  async function upload(files) {if(state.upload||!files.length)return;state.upload=true;$('upload-button').disabled=true;$('upload-progress').hidden=false;const target=state.path;let count=0;
    try{for(const file of files){if(file.size>64*1024*1024)throw new Error('Файл '+file.name+' больше 64 MiB.');const path=(target?target+'/':'')+file.name,meta=await api('/metadata'+query(path));if(meta.exists&&!await confirm('Заменить файл?',path+' уже существует.','Заменить'))continue;$('upload-label').textContent='Загрузка: '+file.name;$('upload-meter').value=0;const result=await sendUpload(file,path,meta.revision);count++;if(!result.fastdl_synced)toast('Файл загружен, но синхронизацию ресурсов нужно проверить.',true);}toast('Загружено файлов: '+count);await listFiles(target);}catch(error){report(error);}finally{state.upload=false;$('upload-button').disabled=false;$('upload-progress').hidden=true;$('upload-input').value='';}}
  $('upload-button').addEventListener('click',()=>$('upload-input').click());$('upload-input').addEventListener('change',()=>upload([...$('upload-input').files]));
  const drop=$('tab-files');drop.addEventListener('dragover',e=>{e.preventDefault();drop.classList.add('dragover');});drop.addEventListener('dragleave',()=>drop.classList.remove('dragover'));drop.addEventListener('drop',e=>{e.preventDefault();drop.classList.remove('dragover');upload([...e.dataTransfer.files]);});
  setInterval(()=>{if(!document.hidden&&state.csrf)refreshStatus();},5000);
  loadSession().catch(()=>showLogin());
})();
