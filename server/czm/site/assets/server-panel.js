(() => {
  'use strict';
  const $=id=>document.getElementById(id), prefix='/api/v1/server-panel', catalog=window.CZM_PANEL_I18N;
  const state={csrf:'',address:'',tab:'overview',path:'',entries:[],edit:null,original:'',loading:false,upload:false,cpu:[],ram:[],generation:0,status:null,info:null,cm:null};
  let lang, toastTimer, confirmResolve, nameResolve, listGeneration=0, notice=null, confirmation=null, naming=null, saving=false;
  try{lang=localStorage.getItem('czm-lang');}catch(_){}
  if(!['ru','en'].includes(lang))lang=/^(ru|uk|be|kk)\b/i.test(navigator.language||'ru')?'ru':'en';
  function t(key,params={}){return (catalog[key]?.[lang]??catalog[key]?.ru??key).replace(/\{(\w+)\}/g,(_,name)=>String(params[name]??''));}
  const locale=()=>lang==='ru'?'ru-RU':'en-GB', query=path=>'?'+new URLSearchParams({path});
  function fail(code,params={}){const e=new Error(code);e.code=code;e.params=params;return e;}
  function errorKey(e){return catalog['error.'+e.code]?'error.'+e.code:catalog[e.code]?e.code:'error.default';}
  function notify(key,params={},error=false){
    notice={key,params,error};const modal=[...document.querySelectorAll('dialog[open]')].at(-1);(modal||document.body).append($('toast'));
    clearTimeout(toastTimer);$('toast').textContent=t(key,params);$('toast').classList.toggle('error',error);$('toast').hidden=false;
    toastTimer=setTimeout(()=>{$('toast').hidden=true;notice=null;},6000);
  }
  const report=e=>notify(errorKey(e),e.params||{},true);
  function bytes(value){
    if(!Number.isFinite(value))return t('Нет данных');
    const units=['B','KiB','MiB','GiB'];let i=0;while(value>=1024&&i<3){value/=1024;i++;}
    return new Intl.NumberFormat(locale(),{minimumFractionDigits:i?1:0,maximumFractionDigits:i?1:0}).format(value)+' '+t('units.'+units[i]);
  }
  const date=value=>new Date(value*1000).toLocaleString(locale(),{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
  const plural=(kind,count)=>t(kind+'.'+new Intl.PluralRules(locale()).select(count),{count});
  function uptime(n){if(!n)return '—';const d=Math.floor(n/86400),h=Math.floor(n%86400/3600),m=Math.floor(n%3600/60);return(d?d+' '+t('units.days')+' ':'')+(h?h+' '+t('units.hours')+' ':'')+m+' '+t('units.minutes');}
  function node(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;}
  async function api(route,options={}){
    const headers={'X-CZM-CSRF':state.csrf,...options.headers};
    if(options.json!==undefined){headers['Content-Type']='application/json';options.body=JSON.stringify(options.json);delete options.json;}
    let response,data;try{response=await fetch(prefix+route,{...options,headers,credentials:'same-origin',cache:'no-store'});}catch(_){throw fail('network');}
    try{data=await response.json();}catch(_){throw fail('network');}
    if(!response.ok){if(response.status===401&&route!=='/login'&&route!=='/session')showLogin();throw fail(data.error||'default');}
    return data;
  }
  function applyLanguage(next,persist=true){
    if(!['ru','en'].includes(next))return;lang=next;if(persist)try{localStorage.setItem('czm-lang',lang);}catch(_){}
    document.documentElement.lang=lang;document.title=t('Панель сервера — Counter Zombie Mobile');
    document.querySelectorAll('[data-i18n]').forEach(e=>{e.textContent=t(e.dataset.i18n);});
    for(const attr of ['aria-label','placeholder','title'])document.querySelectorAll('[data-i18n-'+attr+']').forEach(e=>e.setAttribute(attr,t(e.getAttribute('data-i18n-'+attr))));
    document.querySelectorAll('[data-lang]').forEach(e=>e.setAttribute('aria-pressed',String(e.dataset.lang===lang)));
    $('page-title').textContent=t({overview:'Обзор сервера',console:'Консоль сервера',files:'Файлы сервера',settings:'Настройки сервера'}[state.tab]);
    if(state.status)renderStatus(state.status,false);
    if(state.entries.length||state.tab==='files'){renderFiles();renderCrumbs();}
    if(state.edit){editorChanged();setMode();loadHistory(state.edit.path).catch(report);}
    if(state.info)renderInfo(state.info);
    if(state.loginError&&!$('login-error').hidden)$('login-error').textContent=t(state.loginError);
    if(state.consoleKey)$('console-output').textContent=t(state.consoleKey);
    if(state.searchKey)$('editor-find-state').textContent=t(state.searchKey);
    if(state.uploadName)$('upload-label').textContent=t('uploading',{file:state.uploadName});
    if(confirmation)renderConfirmation();if(naming)renderName();
    if(notice)$('toast').textContent=t(notice.key,notice.params);
    if(state.cm)state.cm.getInputField().setAttribute('aria-label',t('Содержимое документа'));
  }
  document.querySelectorAll('[data-lang]').forEach(e=>e.addEventListener('click',()=>applyLanguage(e.dataset.lang)));
  window.addEventListener('storage',e=>{if(e.key==='czm-lang')applyLanguage(e.newValue,false);});
  function renderConfirmation(){const c=confirmation;$('confirm-title').textContent=t(c.title,c.params);$('confirm-text').textContent=t(c.text,c.params);$('confirm-yes').textContent=t(c.yes);}
  function confirm(title,text,yes='Подтвердить',params={}){return new Promise(resolve=>{confirmation={title,text,yes,params};confirmResolve=resolve;renderConfirmation();$('confirm').showModal();});}
  function resolveConfirm(value){$('confirm').close();confirmation=null;const fn=confirmResolve;confirmResolve=null;if(fn)fn(value);}
  $('confirm-yes').addEventListener('click',()=>resolveConfirm(true));$('confirm-no').addEventListener('click',()=>resolveConfirm(false));
  $('confirm').addEventListener('cancel',e=>{e.preventDefault();resolveConfirm(false);});
  function renderName(){$('name-title').textContent=t(naming.title);$('name-input').placeholder=t(naming.placeholder);}
  function askName(title,placeholder){return new Promise(resolve=>{naming={title,placeholder};nameResolve=resolve;$('name-input').value='';renderName();$('name-dialog').showModal();$('name-input').focus();});}
  function resolveName(value){$('name-dialog').close();naming=null;const fn=nameResolve;nameResolve=null;if(fn)fn(value);}
  $('name-cancel').addEventListener('click',()=>resolveName(null));$('name-dialog').addEventListener('cancel',e=>{e.preventDefault();resolveName(null);});
  $('name-form').addEventListener('submit',e=>{e.preventDefault();resolveName($('name-input').value.trim());});
  function editorText(){return state.cm?state.cm.getValue():$('editor-text').value;}
  function dirty(){return !!state.edit&&(editorText()!==state.original||$('editor-encoding').value!==state.edit.encoding);}
  async function closeEditor(){if(saving)return;if(dirty()&&!await confirm('Закрыть без сохранения?','В документе есть несохранённые изменения.','Закрыть'))return;$('editor').close();state.edit=null;}
  $('editor-close').addEventListener('click',closeEditor);$('editor-cancel').addEventListener('click',closeEditor);
  $('editor').addEventListener('cancel',e=>{e.preventDefault();closeEditor();});
  window.addEventListener('beforeunload',e=>{if(dirty()||state.upload){e.preventDefault();e.returnValue='';}});
  function showLogin(){state.generation++;state.csrf='';$('signin').hidden=false;$('workspace').hidden=true;$('logout').hidden=true;if($('editor').open)$('editor').close();state.edit=null;}
  async function loadSession(){const data=await api('/session');state.csrf=data.csrf;state.address=data.address;$('owner-name').textContent=data.profile.nick;$('server-address').textContent=state.address;$('signin').hidden=true;$('workspace').hidden=false;$('logout').hidden=false;await refreshStatus();}
  $('login-form').addEventListener('submit',async e=>{
    e.preventDefault();const button=$('login-submit');button.disabled=true;$('login-error').hidden=true;state.loginError=null;
    try{await api('/login',{method:'POST',json:{nick:$('login-name').value,password:$('login-password').value}});$('login-password').value='';await loadSession();}
    catch(error){state.loginError=errorKey(error);$('login-error').textContent=t(state.loginError);$('login-error').hidden=false;}finally{button.disabled=false;}
  });
  $('logout').addEventListener('click',async()=>{if(dirty()&&!await confirm('Выйти из панели?','Несохранённые изменения документа будут потеряны.','Выйти'))return;try{await api('/logout',{method:'POST'});showLogin();}catch(e){report(e);}});
  async function switchTab(tab){
    if(!['overview','console','files','settings'].includes(tab))return;state.tab=tab;
    document.querySelectorAll('.panel-nav [data-tab]').forEach(e=>e.classList.toggle('active',e.dataset.tab===tab));
    document.querySelectorAll('.tab-panel').forEach(e=>{e.hidden=e.id!=='tab-'+tab;});
    $('page-title').textContent=t({overview:'Обзор сервера',console:'Консоль сервера',files:'Файлы сервера',settings:'Настройки сервера'}[tab]);
    if(tab==='files')await listFiles(state.path);if(tab==='console')await loadConsole();
  }
  document.querySelectorAll('[data-tab]').forEach(e=>e.addEventListener('click',()=>switchTab(e.dataset.tab).catch(report)));
  function spark(id,values,max){$(id).querySelector('path').setAttribute('d',values.map((n,i)=>(i?'L':'M')+(i*240/Math.max(1,values.length-1)).toFixed(1)+','+(34-Math.min(1,n/Math.max(1,max))*30).toFixed(1)).join(' '));}
  function renderStatus(info,history=true){
    const online=info.state==='active',label=t({active:'Работает',inactive:'Остановлен',failed:'Ошибка запуска',activating:'Запускается',deactivating:'Останавливается'}[info.state]||'Нет данных');
    $('status-pill').querySelector('b').textContent=label;$('status-pill').classList.toggle('online',online);$('sidebar-status').textContent=label;$('sidebar-dot').classList.toggle('online',online);
    $('sync-state').textContent=t('updated',{time:new Date(info.observed_at*1000).toLocaleTimeString(locale(),{hour:'2-digit',minute:'2-digit',second:'2-digit'})});$('sync-state').classList.remove('error');
    const game=info.game;$('server-name').textContent=game?.name||'CZM Zombie Server';$('server-map').textContent=game?.map||'—';$('server-players').textContent=game?game.players+' / '+game.slots:'—';$('server-uptime').textContent=uptime(info.uptime);
    $('cpu-value').textContent=new Intl.NumberFormat(locale(),{minimumFractionDigits:1,maximumFractionDigits:1}).format(info.cpu)+'%';$('cpu-limit').textContent=t('limit',{value:info.cpu_limit+'%'});$('cpu-bar').style.width=Math.min(100,info.cpu/info.cpu_limit*100)+'%';
    $('ram-value').textContent=bytes(info.memory);$('ram-limit').textContent=t('limit',{value:bytes(info.memory_limit)});$('ram-bar').style.width=Math.min(100,info.memory/info.memory_limit*100)+'%';
    $('disk-value').textContent=bytes(info.disk);$('players-value').textContent=game?game.players+' / '+game.slots:'—';
    $('bots-note').textContent=game?plural('bots',game.bots)+' · '+t('Карта').toLocaleLowerCase(locale())+' '+game.map:t('Игровой сервер не отвечает');
    document.querySelectorAll('.players-decoration i').forEach((e,i)=>e.classList.toggle('on',!!game&&i<Math.ceil(game.players/Math.max(1,game.slots)*8)));
    if(history){state.cpu.push(info.cpu);state.ram.push(info.memory);if(state.cpu.length>30){state.cpu.shift();state.ram.shift();}}
    spark('cpu-spark',state.cpu,info.cpu_limit);spark('ram-spark',state.ram,info.memory_limit);
    document.querySelectorAll('[data-power]').forEach(e=>{e.disabled=(e.dataset.power==='start'&&online)||(e.dataset.power==='stop'&&info.state==='inactive');});
  }
  async function refreshStatus(){
    if(!state.csrf||state.loading)return;state.loading=true;const generation=state.generation;
    try{const data=await api('/status');if(generation!==state.generation)return;state.status=data;renderStatus(data);}
    catch(e){$('sync-state').textContent=t('Нет связи · данные устарели');$('sync-state').classList.add('error');document.querySelectorAll('[data-power]').forEach(e=>{e.disabled=true;});}finally{state.loading=false;}
  }
  document.querySelectorAll('[data-power]').forEach(button=>button.addEventListener('click',async()=>{
    const action=button.dataset.power;if(action!=='start'&&!await confirm(action==='stop'?'Остановить сервер?':'Перезапустить сервер?','Подключённые игроки будут отключены.',action==='stop'?'Остановить':'Перезапустить'))return;
    document.querySelectorAll('[data-power]').forEach(e=>{e.disabled=true;});
    try{await api('/power',{method:'POST',json:{action}});notify('Действие выполнено. Обновляем состояние…');await refreshStatus();}catch(e){report(e);await refreshStatus();}
  }));
  $('copy-address').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(state.address);notify('Адрес сервера скопирован.');}catch(_){notify('address',{address:state.address});}});
  async function loadConsole(){try{const data=await api('/console');state.consoleKey=data.text?null:'Журнал пока пуст.';$('console-output').textContent=data.text||t(state.consoleKey);$('console-output').scrollTop=$('console-output').scrollHeight;}catch(e){state.consoleKey=errorKey(e);$('console-output').textContent=t(state.consoleKey);}}
  $('refresh-console').addEventListener('click',loadConsole);
  $('console-form').addEventListener('submit',async e=>{
    e.preventDefault();const input=$('console-command'),command=input.value.trim();if(!command)return;input.disabled=true;
    try{const data=await api('/console',{method:'POST',json:{command}});state.consoleKey=null;$('console-output').textContent=($('console-output').textContent+'\n› '+command+'\n'+data.text).slice(-48000);$('console-output').scrollTop=$('console-output').scrollHeight;input.value='';}catch(error){report(error);}finally{input.disabled=false;input.focus();}
  });
  async function listFiles(path=''){const generation=++listGeneration;$('file-list').replaceChildren(node('div','empty-folder',t('Загрузка папки…')));const data=await api('/files'+query(path));if(generation!==listGeneration)return;state.path=path;state.entries=data.entries;$('file-search').value='';renderFiles();renderCrumbs();}
  function renderCrumbs(){
    $('folder-back').disabled=!state.path;$('folder-back').title=t('Вернуться на уровень выше');
    const root=$('breadcrumbs');root.replaceChildren();const home=node('button','','⌂ '+t('Сервер'));home.type='button';home.addEventListener('click',()=>listFiles('').catch(report));root.append(home);let path='';
    for(const part of state.path.split('/').filter(Boolean)){path+=(path?'/':'')+part;const target=path,button=node('button','',part);button.type='button';button.addEventListener('click',()=>listFiles(target).catch(report));root.append(node('span','','/'),button);}
  }
  $('folder-back').addEventListener('click',()=>{if(state.path)listFiles(state.path.split('/').slice(0,-1).join('/')).catch(report);});
  function fileType(entry){const ext=entry.name.split('.').pop().toLowerCase(),known={wad:'file.texture',bsp:'file.map',mdl:'file.model',amxx:'file.plugin',wav:'file.audio',mp3:'file.audio',png:'file.image',bmp:'file.image',tga:'file.image'};return known[ext]?t(known[ext]):t('file.type',{extension:ext.toUpperCase()});}
  function renderInfo(entry){$('file-info-name').textContent=entry.name;$('file-info-path').textContent=entry.path;$('file-info-type').textContent=fileType(entry);$('file-info-size').textContent=bytes(entry.size);$('file-info-date').textContent=date(entry.modified);}
  function openFile(entry){if(entry.directory)return listFiles(entry.path);if(entry.editable)return openEditor(entry.path);state.info=entry;renderInfo(entry);$('file-info').showModal();return Promise.resolve();}
  function closeInfo(){$('file-info').close();state.info=null;}
  $('file-info-close').addEventListener('click',closeInfo);$('file-info-cancel').addEventListener('click',closeInfo);$('file-info').addEventListener('cancel',e=>{e.preventDefault();closeInfo();});
  $('file-info-download').addEventListener('click',()=>{if(state.info)download(state.info.path);});
  function renderFiles(){
    const term=$('file-search').value.toLocaleLowerCase(locale()),list=$('file-list');list.replaceChildren();const entries=state.entries.filter(e=>e.name.toLocaleLowerCase().includes(term));$('file-count').textContent=plural('objects',entries.length);
    if(!entries.length){list.append(node('div','empty-folder',t(term?'Ничего не найдено.':'Папка пока пустая.')));return;}
    for(const entry of entries){
      const row=node('div','file-row'+(entry.directory?' folder':'')),name=node('button','file-name');name.type='button';name.append(node('span','file-icon',entry.directory?'▱':'▤'),node('span','',entry.name));name.addEventListener('click',()=>openFile(entry).catch(report));
      const size=node('span','file-size',entry.size_complete===false?t('size.partial',{size:bytes(entry.size)}):bytes(entry.size));if(entry.directory)size.title=t('size.explanation');
      row.append(name,size,node('span','file-date',date(entry.modified)));const actions=node('div','file-actions');
      if(!entry.directory){
        if(entry.editable){const edit=node('button','','✎');edit.title=t('Редактировать');edit.setAttribute('aria-label',t('Редактировать')+' '+entry.name);edit.addEventListener('click',()=>openEditor(entry.path).catch(report));actions.append(edit);}
        if(entry.path!=='server.cfg'){const down=node('button','','↓');down.title=t('Скачать');down.setAttribute('aria-label',t('Скачать')+' '+entry.name);down.addEventListener('click',()=>download(entry.path));actions.append(down);}
        const del=node('button','','×');del.title=t('Удалить');del.setAttribute('aria-label',t('Удалить')+' '+entry.name);del.addEventListener('click',()=>deleteFile(entry).catch(report));actions.append(del);
      }row.append(actions);list.append(row);
    }
  }
  $('file-search').addEventListener('input',renderFiles);
  function download(path){const a=node('a');a.href=prefix+'/download'+query(path);a.download=path.split('/').pop();document.body.append(a);a.click();a.remove();}
  async function deleteFile(entry){if(!await confirm('Удалить файл?','delete.detail','Удалить',{path:entry.path}))return;const meta=await api('/metadata'+query(entry.path));await api('/file'+query(entry.path),{method:'DELETE',headers:{'If-Match':meta.revision}});notify('Файл удалён.');await listFiles(state.path);}
  const modes={pawn:'text/x-pawn',lua:'text/x-lua',json:'application/json',cfg:'text/x-properties',javascript:'text/javascript',yaml:'text/x-yaml',xml:'application/xml',text:null};
  function autoMode(path){return{sma:'pawn',inc:'pawn',lua:'lua',json:'json',cfg:'cfg',ini:'cfg',conf:'cfg',js:'javascript',yml:'yaml',yaml:'yaml',xml:'xml'}[path.split('.').pop().toLowerCase()]||'text';}
  function currentMode(){return $('editor-mode').value==='auto'?autoMode(state.edit?.path||''):$('editor-mode').value;}
  function setMode(){const mode=currentMode();$('editor-mode').querySelector('option[value="auto"]').textContent=t('editor.auto',{mode:mode==='text'?t('Текст'):$('editor-mode').querySelector('option[value="'+mode+'"]').textContent});if(state.cm)state.cm.setOption('mode',modes[mode]);}
  function ensureEditor(){
    if(state.cm||!window.CodeMirror)return;const words=text=>Object.fromEntries(text.split(' ').map(key=>[key,true]));
    CodeMirror.defineMIME('text/x-pawn',{name:'clike',keywords:words('new public stock static native forward const enum sizeof tagof state operator if else for while do switch case default break continue return goto assert sleep exit defined'),types:words('Float bool any Handle Array Trie'),atoms:words('true false INVALID_HANDLE'),blockKeywords:words('case do else for if switch while'),defKeywords:words('public stock native forward')});
    state.cm=CodeMirror.fromTextArea($('editor-text'),{lineNumbers:true,mode:null,theme:'czm',indentUnit:4,tabSize:4,smartIndent:true,matchBrackets:true,autoCloseBrackets:true,styleActiveLine:true,lineWrapping:false,
      extraKeys:{'Ctrl-S':()=>saveEditor(),'Cmd-S':()=>saveEditor(),'Ctrl-F':()=>{$('editor-find').focus();},'Cmd-F':()=>{$('editor-find').focus();},'Tab':cm=>{if(cm.somethingSelected())cm.indentSelection('add');else cm.replaceSelection('    ','end','+input');},'Shift-Tab':cm=>cm.indentSelection('subtract'),'Ctrl-/':cm=>cm.toggleComment(),'Cmd-/':cm=>cm.toggleComment()}});
    state.cm.on('change',editorChanged);state.cm.on('cursorActivity',editorChanged);state.cm.getInputField().setAttribute('aria-label',t('Содержимое документа'));
  }
  async function openEditor(path){
    if(dirty()&&!await confirm('Открыть другой документ?','Текущие изменения не сохранены.','Открыть'))return;
    const edit=await api('/file'+query(path));state.edit=edit;state.original=edit.text;$('editor-name').textContent=path.split('/').pop();$('editor-path').textContent=path;
    $('editor-text').value=edit.text;$('editor-encoding').value=edit.encoding;$('editor-mode').value='auto';$('editor-find').value='';$('editor-find-state').textContent='';state.searchKey=null;
    $('protected-note').hidden=!edit.protected;if(!$('editor').open)$('editor').showModal();ensureEditor();setMode();
    if(state.cm){state.cm.setValue(edit.text);state.cm.clearHistory();state.cm.setCursor(0,0);requestAnimationFrame(()=>{state.cm.refresh();state.cm.focus();});}
    editorChanged();await loadHistory(path);
  }
  document.querySelectorAll('[data-open]').forEach(button=>button.addEventListener('click',()=>openEditor(button.dataset.open).catch(report)));
  function editorChanged(){const pos=state.cm?state.cm.getCursor():{line:0,ch:0};$('editor-state').textContent=t(dirty()?'Есть несохранённые изменения':'Изменения сохранены');$('editor-state').classList.toggle('dirty',dirty());$('editor-lines').textContent=t('editor.lines',{count:editorText().split('\n').length,line:pos.line+1,column:pos.ch+1});}
  $('editor-text').addEventListener('input',editorChanged);$('editor-encoding').addEventListener('change',editorChanged);$('editor-mode').addEventListener('change',setMode);
  $('editor-wrap').addEventListener('click',()=>{if(!state.cm)return;const value=!state.cm.getOption('lineWrapping');state.cm.setOption('lineWrapping',value);$('editor-wrap').setAttribute('aria-pressed',String(value));});
  $('editor-indent').addEventListener('click',()=>{if(state.cm){state.cm.getOption('extraKeys').Tab(state.cm);state.cm.focus();}});
  $('editor-undo').addEventListener('click',()=>{if(state.cm)state.cm.undo();});
  $('editor-redo').addEventListener('click',()=>{if(state.cm)state.cm.redo();});
  function search(back=false){
    if(!state.cm)return;const term=$('editor-find').value;if(!term){$('editor-find-state').textContent='';state.searchKey=null;return;}
    const cm=state.cm,start=cm.getCursor(back?'from':'to');let cursor=cm.getSearchCursor(term,start,{caseFold:true}),found=back?cursor.findPrevious():cursor.findNext();
    if(!found){cursor=cm.getSearchCursor(term,back?CodeMirror.Pos(cm.lastLine(),cm.getLine(cm.lastLine()).length):CodeMirror.Pos(0,0),{caseFold:true});found=back?cursor.findPrevious():cursor.findNext();}
    state.searchKey=found?'editor.search_found':'Не найдено';$('editor-find-state').textContent=t(state.searchKey);if(found){cm.setSelection(cursor.from(),cursor.to());cm.scrollIntoView({from:cursor.from(),to:cursor.to()},50);}
  }
  $('editor-find-next').addEventListener('click',()=>search());$('editor-find-prev').addEventListener('click',()=>search(true));$('editor-find').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();search(e.shiftKey);}});
  async function saveEditor(){
    if(!state.edit||saving)return;saving=true;$('editor-save').disabled=true;$('editor-cancel').disabled=true;
    const edit=state.edit,text=editorText(),encoding=$('editor-encoding').value;
    try{const result=await api('/file',{method:'POST',json:{path:edit.path,text,revision:edit.revision,encoding}});if(state.edit!==edit)return;edit.revision=result.revision;edit.encoding=encoding;state.original=text;editorChanged();notify('Документ сохранён. Резервная копия создана.');await loadHistory(edit.path);if(!result.fastdl_synced)notify('Документ сохранён, но загрузку ресурсов нужно проверить.',{},true);}
    catch(error){report(error);}finally{saving=false;$('editor-save').disabled=false;$('editor-cancel').disabled=false;}
  }
  $('editor-save').addEventListener('click',saveEditor);
  async function loadHistory(path){
    const root=$('history-list');root.replaceChildren();const data=await api('/history'+query(path));
    for(const entry of data.entries){const row=node('div','history-row');row.append(node('span','',date(entry.created)+' · '+bytes(entry.size)));const button=node('button','',t('Восстановить'));button.addEventListener('click',async()=>{
      if(!await confirm('Восстановить копию?','restore.detail','Восстановить',{date:date(entry.created)}))return;
      try{await api('/restore',{method:'POST',json:{path,revision:state.edit.revision,backup:entry.id}});state.edit=null;await openEditor(path);notify('Копия восстановлена.');}catch(e){report(e);}
    });row.append(button);root.append(row);}if(!data.entries.length)root.append(node('p','footnote',t('Копии появятся после первого изменения документа. Хранятся 10 последних версий.')));
  }
  $('new-folder').addEventListener('click',async()=>{try{const name=await askName('Новая папка','Название папки');if(!name)return;await api('/directory',{method:'POST',json:{path:(state.path?state.path+'/':'')+name}});await listFiles(state.path);notify('Папка создана.');}catch(e){report(e);}});
  $('new-file').addEventListener('click',async()=>{try{const name=await askName('Новый документ','Например custom.cfg');if(!name)return;const path=(state.path?state.path+'/':'')+name;await api('/file',{method:'POST',json:{path,text:'',revision:'new',encoding:'utf-8'}});await listFiles(state.path);await openEditor(path);}catch(e){report(e);}});
  function sendUpload(file,path,revision){return new Promise((resolve,reject)=>{
    const xhr=new XMLHttpRequest();xhr.open('PUT',prefix+'/upload'+query(path));xhr.setRequestHeader('X-CZM-CSRF',state.csrf);xhr.setRequestHeader('If-Match',revision);xhr.setRequestHeader('Content-Type','application/octet-stream');xhr.timeout=180000;
    xhr.upload.onprogress=e=>{if(e.lengthComputable)$('upload-meter').value=e.loaded/e.total*100;};
    xhr.onload=()=>{let data;try{data=JSON.parse(xhr.responseText);}catch(_){reject(fail('upload'));return;}if(xhr.status>=200&&xhr.status<300)resolve(data);else reject(fail(data.error||'upload'));};
    xhr.onerror=()=>reject(fail('upload_connection'));xhr.ontimeout=()=>reject(fail('upload_timeout'));xhr.send(file);
  });}
  async function upload(files){
    if(state.upload||!files.length)return;state.upload=true;$('upload-button').disabled=true;$('upload-progress').hidden=false;const target=state.path;let count=0;
    try{for(const file of files){if(file.size>64*1024*1024)throw fail('upload.large',{file:file.name});const path=(target?target+'/':'')+file.name,meta=await api('/metadata'+query(path));if(meta.exists&&!await confirm('Заменить файл?','replace.detail','Заменить',{path}))continue;
      state.uploadName=file.name;$('upload-label').textContent=t('uploading',{file:file.name});$('upload-meter').value=0;const result=await sendUpload(file,path,meta.revision);count++;if(!result.fastdl_synced)notify('Файл загружен, но синхронизацию ресурсов нужно проверить.',{},true);
    }notify('uploaded',{count});await listFiles(target);}catch(e){report(e);}finally{state.upload=false;state.uploadName=null;$('upload-button').disabled=false;$('upload-progress').hidden=true;$('upload-input').value='';}
  }
  $('upload-button').addEventListener('click',()=>$('upload-input').click());$('upload-input').addEventListener('change',()=>upload([...$('upload-input').files]));
  const drop=$('tab-files');drop.addEventListener('dragover',e=>{e.preventDefault();drop.classList.add('dragover');});drop.addEventListener('dragleave',()=>drop.classList.remove('dragover'));drop.addEventListener('drop',e=>{e.preventDefault();drop.classList.remove('dragover');upload([...e.dataTransfer.files]);});
  applyLanguage(lang,false);setInterval(()=>{if(!document.hidden&&state.csrf)refreshStatus();},5000);loadSession().catch(()=>showLogin());
})();
