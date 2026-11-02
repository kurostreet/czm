const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {JSDOM,VirtualConsole}=require('jsdom');
const site=path.join(__dirname,'../site');
const html=fs.readFileSync(path.join(site,'server-panel.html'),'utf8');
const css=fs.readFileSync(path.join(site,'assets/server-panel.css'),'utf8');
const scripts=['assets/vendor/codemirror.js','assets/server-panel-i18n.js','assets/server-panel.js'].map(p=>fs.readFileSync(path.join(site,p),'utf8'));
const tick=()=>new Promise(r=>setTimeout(r,35));

async function panel(lang='ru',fixture={}){
  const errors=[],requests=[],downloads=[];
  const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e));
  const dom=new JSDOM(html,{url:'https://counter-zombie.ru/server-panel',runScripts:'outside-only',pretendToBeVisual:true,virtualConsole:vc});
  const w=dom.window,d=w.document;
  w.focus=()=>{}; // No OS window exists in these DOM integration tests.
  w.localStorage.setItem('czm-lang',lang);
  w.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};
  w.HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');};
  w.HTMLAnchorElement.prototype.click=function(){downloads.push(this.href);};
  const rect={left:0,right:500,top:0,bottom:20,width:500,height:20,x:0,y:0};
  w.Range.prototype.getBoundingClientRect=()=>rect;w.Range.prototype.getClientRects=()=>[rect];
  w.HTMLElement.prototype.getBoundingClientRect=()=>rect;
  const file={name:'custom.cfg',path:'custom.cfg',directory:false,editable:true,size:18,modified:1793630000,size_complete:true};
  const wad={name:'textures.wad',path:'textures.wad',directory:false,editable:false,size:48460,modified:1793630000,size_complete:true};
  const folders={
    '':[{name:'addons',path:'addons',directory:true,size:3210,size_complete:true,modified:1793630000},file,wad],
    'addons':[{name:'amxmodx',path:'addons/amxmodx',directory:true,size:3210,size_complete:true,modified:1793630000}],
    'addons/amxmodx':[{name:'configs',path:'addons/amxmodx/configs',directory:true,size:100,size_complete:true,modified:1793630000}]
  };
  let text='hostname "original"\n',revision='original',conflict=false,saveGate;
  w.fetch=async(url,options={})=>{
    const u=new URL(url,w.location.origin),route=u.pathname.replace('/api/v1/server-panel',''),method=options.method||'GET';
    const body=options.body?JSON.parse(options.body):undefined;
    requests.push({route,method,body,path:u.searchParams.get('path')});
    let data={},status=200;
    if(route==='/session'){
      if(fixture.anonymous){status=401;data={error:'auth'};}
      else data={csrf:'fixture-csrf',profile:{id:1,nick:'Operator'},address:'192.0.2.1:27016'};
    }
    else if(route==='/login'){status=401;data={error:'credentials'};}
    else if(route==='/status')data={state:'active',cpu:3.5,cpu_limit:35,memory:100000000,memory_limit:335544320,disk:400000000,uptime:61,observed_at:1793630000,game:{name:'CZM Test',map:'zm_test',players:1,slots:32,bots:1}};
    else if(route==='/files')data={path:u.searchParams.get('path')||'',entries:folders[u.searchParams.get('path')||'']||[]};
    else if(route==='/file'&&method==='GET')data={path:u.searchParams.get('path'),text,revision,encoding:'utf-8',protected:false};
    else if(route==='/file'&&method==='POST'){
      assert.equal(options.headers['X-CZM-CSRF'],'fixture-csrf');
      if(saveGate)await saveGate;
      if(conflict||body.revision!==revision){status=409;data={error:'conflict'};}
      else{text=body.text;revision+='x';data={ok:true,revision,fastdl_synced:true};}
    }else if(route==='/history')data={entries:[]};
    else if(route==='/console')data={text:fixture.emptyConsole?'':'Game console ready'};
    return{ok:status===200,status,json:async()=>data};
  };
  for(const source of scripts)w.eval(source);
  await tick();
  const click=(selector)=>{const e=d.querySelector(selector);assert.ok(e,selector);e.click();return tick();};
  const byName=(name)=>[...d.querySelectorAll('.file-name')].find(e=>e.textContent.includes(name));
  return{w,d,dom,errors,requests,downloads,click,byName,get text(){return text;},forceConflict(){conflict=true;},delaySave(){let release;saveGate=new Promise(r=>{release=r;});return()=>{release();saveGate=null;};}};
}

test('RU/EN translates all static controls and shares the main-site preference',async t=>{
  const p=await panel('ru');t.after(()=>p.dom.window.close());
  assert.equal(p.d.documentElement.lang,'ru');
  await p.click('[data-lang="en"]');
  assert.equal(p.w.localStorage.getItem('czm-lang'),'en');assert.equal(p.d.documentElement.lang,'en');
  assert.equal(p.d.querySelector('#editor-save').textContent.trim(),'Save');assert.equal(p.d.querySelector('#editor-cancel').textContent.trim(),'Cancel');
  assert.equal(p.d.querySelector('#file-search').placeholder,'Find in this folder');
  assert.equal(p.d.querySelector('#page-title').textContent,'Server overview');
  assert.ok(!/[А-Яа-яЁё]/.test(p.d.body.textContent),'Untranslated UI text remains in English');
  assert.equal(p.d.querySelector('#server-players').textContent,'1 / 32');
  await p.click('[data-lang="ru"]');assert.equal(p.d.querySelector('#editor-cancel').textContent.trim(),'Отмена');
  assert.deepEqual(p.errors,[]);
});

test('folder Back moves one level and root disables it; folder sizes stay numeric',async t=>{
  const p=await panel();t.after(()=>p.dom.window.close());await p.click('.panel-nav [data-tab="files"]');
  assert.ok(p.d.querySelector('#folder-back').disabled);
  assert.match(p.d.querySelector('.folder .file-size').textContent,/КиБ/);
  p.byName('addons').click();await tick();assert.equal(p.d.querySelector('#folder-back').disabled,false);
  p.byName('amxmodx').click();await tick();assert.match(p.d.querySelector('#breadcrumbs').textContent,/amxmodx/);
  await p.click('#folder-back');assert.match(p.d.querySelector('#breadcrumbs').textContent,/addons/);assert.ok(!p.d.querySelector('#breadcrumbs').textContent.includes('amxmodx'));
  await p.click('#folder-back');assert.ok(p.d.querySelector('#folder-back').disabled);assert.ok(p.byName('custom.cfg'));
});

test('clicking a text filename opens the online code editor; Save updates server content',async t=>{
  const p=await panel();t.after(()=>p.dom.window.close());await p.click('.panel-nav [data-tab="files"]');p.byName('custom.cfg').click();await tick();
  assert.ok(p.d.querySelector('#editor').open);const cm=p.d.querySelector('.CodeMirror').CodeMirror;
  assert.ok(cm.getOption('lineNumbers'));assert.equal(cm.getValue(),p.text);assert.equal(p.downloads.length,0);
  cm.setValue('hostname "updated"\n');await p.click('#editor-save');
  assert.equal(p.text,'hostname "updated"\n');assert.match(p.d.querySelector('#editor-state').textContent,/сохранены/);
  assert.equal(p.requests.filter(r=>r.route==='/file'&&r.method==='POST').length,1);
  assert.deepEqual(p.errors,[]);
});

test('Cancel keeps unsaved text until discard confirmation and does not write the file',async t=>{
  const p=await panel();t.after(()=>p.dom.window.close());await p.click('[data-open="server.cfg"]');
  const cm=p.d.querySelector('.CodeMirror').CodeMirror;cm.setValue('unsaved changes');
  await p.click('#editor-cancel');assert.ok(p.d.querySelector('#confirm').open);
  await p.click('#confirm-no');assert.ok(p.d.querySelector('#editor').open);assert.equal(cm.getValue(),'unsaved changes');
  await p.click('#editor-cancel');await p.click('#confirm-yes');assert.equal(p.d.querySelector('#editor').open,false);
  assert.equal(p.text,'hostname "original"\n');assert.equal(p.requests.filter(r=>r.method==='POST').length,0);
});

test('binary filename opens details; only the small download button downloads',async t=>{
  const p=await panel('en');t.after(()=>p.dom.window.close());await p.click('.panel-nav [data-tab="files"]');
  p.byName('textures.wad').click();await tick();assert.ok(p.d.querySelector('#file-info').open);assert.equal(p.downloads.length,0);
  assert.match(p.d.querySelector('#file-info-type').textContent,/WAD/);assert.match(p.d.querySelector('#file-info-size').textContent,/KiB/);
  await p.click('#file-info-close');await p.click('button[aria-label="Download textures.wad"]');assert.equal(p.downloads.length,1);assert.match(p.downloads[0],/download/);
});

test('syntax choice, indentation and search work; changing language preserves unsaved code',async t=>{
  const p=await panel();t.after(()=>p.dom.window.close());await p.click('[data-open="server.cfg"]');const cm=p.d.querySelector('.CodeMirror').CodeMirror;
  cm.setValue('local value = 3\nprint(value)\n');const select=p.d.querySelector('#editor-mode');select.value='lua';select.dispatchEvent(new p.w.Event('change'));
  assert.equal(cm.getOption('mode'),'text/x-lua');cm.setCursor(0,0);cm.getOption('extraKeys').Tab(cm);assert.match(cm.getValue(),/^    local/);
  p.d.querySelector('#editor-find').value='value';await p.click('#editor-find-next');assert.equal(cm.getSelection(),'value');
  const code=cm.getValue();await p.click('[data-lang="en"]');assert.equal(cm.getValue(),code);assert.equal(p.d.querySelector('#editor-state').textContent,'Unsaved changes');
  assert.equal(p.d.querySelector('#editor-find-state').textContent,p.w.CZM_PANEL_I18N['editor.search_found'].en);
  assert.equal(p.d.querySelector('#editor-save').textContent.trim(),'Save');assert.equal(p.requests.filter(r=>r.method==='POST').length,0);
});

test('a conflicting save keeps local edits and reports the conflict in English',async t=>{
  const p=await panel('en');t.after(()=>p.dom.window.close());await p.click('[data-open="server.cfg"]');const cm=p.d.querySelector('.CodeMirror').CodeMirror;
  cm.setValue('keep my edits');p.forceConflict();await p.click('#editor-save');
  assert.equal(cm.getValue(),'keep my edits');assert.equal(p.text,'hostname "original"\n');assert.match(p.d.querySelector('#toast').textContent,/document has changed/);
  assert.ok(p.d.querySelector('#editor').open);
});

test('typing during a slow save stays unsaved until the next Save',async t=>{
  const p=await panel('en');t.after(()=>p.dom.window.close());await p.click('[data-open="server.cfg"]');const cm=p.d.querySelector('.CodeMirror').CodeMirror;
  cm.setValue('first version');const release=p.delaySave();await p.click('#editor-save');assert.ok(p.d.querySelector('#editor-save').disabled);
  cm.setValue('second version');release();await tick();assert.equal(p.text,'first version');assert.equal(cm.getValue(),'second version');
  assert.equal(p.d.querySelector('#editor-state').textContent,'Unsaved changes');
  await p.click('#editor-save');assert.equal(p.text,'second version');assert.equal(p.d.querySelector('#editor-state').textContent,'Changes saved');
});

test('translated labels retain text styling instead of icon widths and hidden arrow styling',()=>{
  const dom=new JSDOM('<style>'+css+'</style>'+html),w=dom.window,d=w.document;
  for(const selector of ['.panel-nav button [data-i18n]','.power-actions button [data-i18n]']){
    for(const label of d.querySelectorAll(selector))assert.ok(!/^\d+px$/.test(w.getComputedStyle(label).width),selector);
  }
  assert.ok(!css.includes('.console-input .primary>span{display:none}'));
  assert.ok(css.includes('.console-input .primary>span:last-child{display:none}'));
  w.close();
});

test('visible sign-in errors follow a language switch without another login attempt',async t=>{
  const p=await panel('ru',{anonymous:true});t.after(()=>p.dom.window.close());
  p.d.querySelector('#login-password').value='fixture-invalid';p.d.querySelector('#login-form').dispatchEvent(new p.w.Event('submit',{cancelable:true}));await tick();
  assert.equal(p.d.querySelector('#login-error').hidden,false);assert.equal(p.d.querySelector('#login-error').textContent,p.w.CZM_PANEL_I18N['error.credentials'].ru);
  await p.click('[data-lang="en"]');assert.equal(p.d.querySelector('#login-error').textContent,p.w.CZM_PANEL_I18N['error.credentials'].en);
  assert.equal(p.requests.filter(r=>r.route==='/login').length,1);
});

test('an empty console translates immediately when the language changes',async t=>{
  const p=await panel('ru',{emptyConsole:true});t.after(()=>p.dom.window.close());await p.click('.panel-nav [data-tab="console"]');
  assert.equal(p.d.querySelector('#console-output').textContent,'Журнал пока пуст.');
  await p.click('[data-lang="en"]');assert.equal(p.d.querySelector('#console-output').textContent,p.w.CZM_PANEL_I18N['Журнал пока пуст.'].en);
});
