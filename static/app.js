/* EvidenceDesk browser client. Untrusted strings enter the DOM as text only. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const state = {sessionId:null, library:[], controller:null, started:0, timer:null, lastResponse:null};
  const storageKey = 'evidencedesk-session-v1';
  const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }
  function array(value) { return Array.isArray(value) ? value : []; }
  function stringify(value) {
    if (typeof value === 'string') return value;
    try { return JSON.stringify(value, null, 2); } catch (_) { return String(value); }
  }
  function urlLink(url, label) {
    try {
      const parsed = new URL(String(url));
      if (!['https:', 'http:'].includes(parsed.protocol)) return el('span', '', label);
      const link = el('a', '', label);
      link.href = parsed.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
      return link;
    } catch (_) { return el('span', '', label); }
  }
  function newUuid() {
    if (crypto.randomUUID) return crypto.randomUUID();
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
    const hex = [...bytes].map(b => b.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
  }
  function setSession(value) {
    state.sessionId = uuidPattern.test(String(value)) ? String(value) : newUuid();
    try { localStorage.setItem(storageKey, state.sessionId); } catch (_) {}
    $('session-label').textContent = `Session ${state.sessionId.slice(0,8)}`;
  }
  async function api(url, options = {}, timeout = 180000) {
    const ownController = options.signal ? null : new AbortController();
    const timer = ownController ? setTimeout(() => ownController.abort(), timeout) : null;
    try {
      const response = await fetch(url, {headers:{'Content-Type':'application/json'}, ...options, signal:options.signal || ownController.signal});
      let data;
      try { data = await response.json(); } catch (_) { throw new Error(`The server returned an unreadable response (HTTP ${response.status}).`); }
      if (!response.ok) {
        const detail = data.error ?? data.detail ?? `Request failed (HTTP ${response.status}).`;
        throw new Error(typeof detail === 'string' ? detail : stringify(detail));
      }
      return data;
    } finally { if (timer) clearTimeout(timer); }
  }
  function showError(message) {
    $('request-error').textContent = message;
    $('request-error').hidden = !message;
  }
  function setBusy(busy) {
    for (const id of ['send-button','new-conversation','mode-select','use-cache']) $(id).disabled = busy;
    $('message-input').disabled = busy;
    for (const button of document.querySelectorAll('.quick-prompt')) button.disabled = busy;
    $('request-status').hidden = !busy;
    if (busy) {
      state.started = performance.now();
      $('request-status-text').textContent = 'Processing request with the local system';
      state.timer = setInterval(() => {
        const seconds = Math.floor((performance.now() - state.started) / 1000);
        $('request-status-text').textContent = `Processing request · ${seconds}s elapsed`;
      }, 1000);
    } else {
      clearInterval(state.timer); state.timer = null;
    }
  }
  function scrollConversation() {
    const log = $('conversation-log'); log.scrollTop = log.scrollHeight;
  }
  function hideWelcome() { const welcome = $('welcome'); if (welcome) welcome.hidden = true; }
  function message(role, content, response) {
    hideWelcome();
    const article = el('article', `message ${role}`);
    const header = el('div','message-header');
    header.append(el('span','speaker-icon',role === 'user' ? 'Y' : 'E'));
    header.append(el('span','',role === 'user' ? 'You' : 'EvidenceDesk'));
    if (response && Number.isFinite(response.latency_seconds)) header.append(el('span','message-meta',`${response.latency_seconds.toFixed(1)} seconds`));
    article.append(header, el('div','message-body',content));
    if (response?.abstained) article.append(el('span','answer-state','Insufficient supporting evidence'));
    if (response) {
      const button = el('button','message-evidence-button','Inspect this response'); button.type='button';
      button.addEventListener('click',() => { renderResponse(response); selectPanel('evidence'); });
      article.append(button);
    }
    $('conversation-log').append(article); scrollConversation();
    return article;
  }
  function emptyPanel(panel, title, description) {
    const box = el('div','panel-empty'); box.append(el('h3','',title), el('p','',description));
    panel.replaceChildren(box);
  }
  function renderSources(response) {
    const panel = $('panel-evidence'); panel.replaceChildren();
    const sources = array(response.sources); $('sources-count').textContent = sources.length;
    if (!sources.length) { emptyPanel(panel,'No retrieved passages','This response did not include retrieved source passages. Inspect the mode and tool trace.'); return; }
    for (const source of sources) {
      const card = el('article','source-card');
      const meta = el('div','source-meta'); meta.append(el('span','source-id',source.id ?? 'Source'));
      if (source.year) meta.append(el('span','',source.year));
      if (source.source_type) meta.append(el('span','',source.source_type));
      if (Number.isFinite(source.score)) meta.append(el('span','',`Similarity ${source.score.toFixed(3)}`));
      card.append(meta,el('h3','',source.title || 'Untitled source'));
      if (source.url) card.append(urlLink(source.url,'Open original source ↗'));
      const detail = el('details',''); detail.open = sources.length === 1;
      detail.append(el('summary','','Read retrieved passage'),el('p','source-passage',source.text ?? 'No passage text returned.'));
      card.append(detail); panel.append(card);
    }
  }
  function renderAudit(response) {
    const panel=$('panel-audit'); panel.replaceChildren();
    const audit=response.audit || {}; const claims=array(response.claims);
    $('claims-count').textContent=claims.length;
    const summary=el('div','audit-summary');
    const passed=Number.isFinite(audit.passed) ? audit.passed : null;
    const total=Number.isFinite(audit.total) ? audit.total : claims.length;
    summary.append(el('h3','',passed === null ? 'Audit result' : `${passed} of ${total} checks passed`));
    summary.append(el('p','',audit.scope || 'Inspect the returned checks and supporting passages to understand audit scope.'));
    panel.append(summary);
    if (!claims.length) panel.append(el('p','section-note',response.abstained ? 'The system abstained. There are no generated claims to audit.' : 'No individual claim records were returned for this response.'));
    for (const claim of claims) {
      const card=el('article','claim-card');
      const valid=claim.valid === true; const known=typeof claim.valid === 'boolean';
      card.append(el('span',`check-state${known ? (valid ? '' : ' failed') : ' unknown'}`,known ? (valid ? 'Check passed' : 'Check flagged') : 'No check status'));
      if (claim.source_id) card.append(el('span','source-id',` ${claim.source_id}`));
      card.append(el('h3','',claim.text ?? 'Claim'));
      if (claim.reason) card.append(el('p','reason',claim.reason));
      if (claim.quote) card.append(el('blockquote','',claim.quote));
      panel.append(card);
    }
  }
  function renderTrace(response) {
    const panel=$('panel-trace'); panel.replaceChildren();
    const plan=response.plan;
    if (plan && typeof plan === 'object') {
      const box=el('div','trace-plan'); box.append(el('h3','','Agent plan'));
      for (const key of ['action','query','doi','origin']) if (plan[key]) box.append(el('p','',`${key}: ${stringify(plan[key])}`));
      panel.append(box);
    }
    const trace=array(response.trace);
    if (trace.length) panel.append(el('h3','trace-title','Execution record'));
    for (const step of trace) {
      const box=el('article','trace-step'); const head=el('div','trace-step-header');
      head.append(el('strong','',step.step ?? 'Step'));
      const duration=Number.isFinite(step.milliseconds) ? ` · ${Math.round(step.milliseconds)} ms` : '';
      head.append(el('span','',`${step.status ?? ''}${duration}`));
      box.append(head,el('p','',typeof step.detail === 'string' ? step.detail : stringify(step.detail ?? ''))); panel.append(box);
    }
    const results=array(response.tool_results);
    if (results.length) panel.append(el('h3','trace-title','Tool outputs'));
    for (const result of results) {
      const detail=el('details','tool-result');
      detail.append(el('summary','',`${result.tool ?? 'Tool'} · ${result.ok ? 'completed' : 'error'}`));
      if (result.cache_status) detail.append(el('p','tool-state',`Cache status: ${result.cache_status}`));
      if (result.error) detail.append(el('p','quotation-error',typeof result.error === 'string' ? result.error : stringify(result.error)));
      if (result.data !== undefined) detail.append(el('pre','',stringify(result.data)));
      panel.append(detail);
    }
    if (!plan && !trace.length && !results.length) emptyPanel(panel,'No tool record','This response did not include an agent plan or tool trace.');
  }
  function renderResponse(response) {
    state.lastResponse=response; renderSources(response); renderAudit(response); renderTrace(response);
    $('response-time').textContent=Number.isFinite(response.latency_seconds) ? `${response.latency_seconds.toFixed(1)}s` : '';
  }
  function selectPanel(name) {
    for (const button of document.querySelectorAll('[data-panel]')) {
      const selected=button.dataset.panel === name;
      button.setAttribute('aria-selected',String(selected)); button.tabIndex=selected ? 0 : -1;
      $(`panel-${button.dataset.panel}`).hidden=!selected;
    }
  }
  async function submitQuestion(value) {
    const question=String(value).trim(); if (!question || state.controller) return;
    showError(''); message('user',question); $('message-input').value=''; $('message-input').style.height='';
    state.controller=new AbortController(); setBusy(true);
    const timeout=setTimeout(() => state.controller?.abort(),240000);
    try {
      const data=await api('/api/chat',{method:'POST',signal:state.controller.signal,body:JSON.stringify({message:question,session_id:state.sessionId,mode:$('mode-select').value,use_cache:$('use-cache').checked})});
      if (data.session_id && uuidPattern.test(String(data.session_id))) setSession(data.session_id);
      message('assistant',data.answer ?? 'The server returned no answer text.',data); renderResponse(data);
      selectPanel(data.abstained ? 'audit' : 'evidence');
    } catch(error) {
      showError(error.name === 'AbortError' ? 'Stopped waiting for this request. The server may still be processing it. You can refresh this conversation later.' : error.message || 'The request could not be completed.');
    } finally {
      clearTimeout(timeout); state.controller=null; setBusy(false); $('message-input').focus();
    }
  }
  async function loadHistory() {
    const requestedSession=state.sessionId;
    try {
      const data=await api(`/api/history?session_id=${encodeURIComponent(requestedSession)}`,{},15000);
      if (state.sessionId !== requestedSession || $('conversation-log').querySelector('.message')) return;
      const turns=array(data.turns);
      for (const turn of turns) {
        message('user',turn.question ?? '');
        const response=typeof turn.response === 'object' && turn.response !== null ? turn.response : {answer:String(turn.response ?? '')};
        message('assistant',response.answer ?? '',response); renderResponse(response);
      }
    } catch(error) { showError(`Conversation history could not be loaded: ${error.message}`); }
  }
  async function refreshHealth() {
    const status=$('health-status');
    try {
      const data=await api('/api/health',{},15000);
      const ready=Boolean(data.models?.llm && data.models?.embeddings);
      status.className=`status-label ${ready ? 'ready' : 'pending'}`;
      status.replaceChildren(el('span','status-dot'),document.createTextNode(ready ? 'Local models ready' : 'Local models not ready'));
      $('model-label').textContent=typeof data.model === 'string' ? data.model : 'Qwen3-0.6B Q4_K_M';
      $('embedding-label').textContent=typeof data.embedding === 'string' ? data.embedding : 'MiniLM · 384 dimensions';
      if (Number.isFinite(data.corpus_size)) $('library-count').textContent=data.corpus_size;
    } catch(_) {
      status.className='status-label error'; status.replaceChildren(el('span','status-dot'),document.createTextNode('Server unavailable'));
    }
  }
  async function loadLibrary() {
    try {
      const data=await api('/api/library',{},15000); state.library=array(data.documents);
      $('library-count').textContent=state.library.length;
      $('library-content').replaceChildren(); $('quotation-source').replaceChildren();
      for (const doc of state.library) {
        const article=el('article','library-document');
        article.append(el('h3','',`${doc.id ?? ''} — ${doc.title ?? 'Untitled source'}`));
        const authors=Array.isArray(doc.authors) ? doc.authors.join(', ') : doc.authors;
        article.append(el('p','',[doc.year,authors].filter(Boolean).join(' · ')));
        article.append(el('p','',`Source: ${doc.source_type ?? 'Not specified'} · License: ${doc.license ?? 'Not specified'}`));
        if (doc.doi) article.append(el('p','',`DOI: ${doc.doi}`));
        if (doc.url) article.append(urlLink(doc.url,'Open source ↗'));
        $('library-content').append(article);
        const option=el('option','',`${doc.id} — ${doc.title}`); option.value=String(doc.id); $('quotation-source').append(option);
      }
      if (state.library.some(doc => doc.id === 'P06')) $('quotation-source').value='P06';
      if (!state.library.length) $('library-content').append(el('p','section-note','The server returned an empty source library.'));
    } catch(error) { $('library-content').replaceChildren(el('p','quotation-error',`Source library could not be loaded: ${error.message}`)); }
  }
  function resetConversation() {
    if (state.controller) return;
    setSession(newUuid()); showError(''); state.lastResponse=null;
    const welcome=$('welcome');
    for (const child of [...$('conversation-log').children]) if (child !== welcome) child.remove();
    if (welcome) welcome.hidden=false;
    emptyPanel($('panel-evidence'),'Passages appear here','Run a question to inspect the retrieved sources.');
    emptyPanel($('panel-audit'),'No audit yet','Claim checks will appear after an agent response.');
    emptyPanel($('panel-trace'),'No tool calls yet','Actual planning and tool outcomes will appear here.');
    $('sources-count').textContent='0'; $('claims-count').textContent='0'; $('response-time').textContent='';
    selectPanel('evidence'); $('message-input').focus();
  }
  async function submitQuotation(event) {
    event.preventDefault(); const button=$('quotation-submit'); button.disabled=true;
    $('quotation-result').replaceChildren(el('p','section-note','Running the custom evidence audit…'));
    try {
      const sourceId=$('quotation-source').value;
      const result=await api('/api/audit',{method:'POST',body:JSON.stringify({claims:[{text:$('quotation-claim').value.trim(),source_id:sourceId,quote:$('quotation-text').value.trim()}],source_ids:[sourceId]})},30000);
      const audit=result.audit || result; const output=$('quotation-result'); output.replaceChildren();
      if (Number.isFinite(audit.passed) && Number.isFinite(audit.total)) {
        const summary=el('div','audit-summary'); summary.append(el('h3','',`${audit.passed} of ${audit.total} checks passed`));
        if (audit.scope) summary.append(el('p','',audit.scope)); output.append(summary);
      }
      const detail=el('details','raw-audit'); detail.open=true; detail.append(el('summary','','Returned audit record'),el('pre','',stringify(result))); output.append(detail);
    } catch(error) { $('quotation-result').replaceChildren(el('p','quotation-error',error.name === 'AbortError' ? 'The quotation audit timed out. Please try again.' : error.message)); }
    finally { button.disabled=false; }
  }

  $('chat-form').addEventListener('submit',event => {event.preventDefault(); submitQuestion($('message-input').value);});
  $('message-input').addEventListener('keydown',event => {if(event.key === 'Enter' && !event.shiftKey && !event.isComposing){event.preventDefault(); $('chat-form').requestSubmit();}});
  $('message-input').addEventListener('input',event => {event.target.style.height='auto';event.target.style.height=`${Math.min(event.target.scrollHeight,130)}px`;});
  for (const button of document.querySelectorAll('.quick-prompt')) button.addEventListener('click',() => submitQuestion(button.dataset.prompt));
  for (const button of document.querySelectorAll('[data-panel]')) {
    button.addEventListener('click',() => selectPanel(button.dataset.panel));
    button.addEventListener('keydown',event => {
      if (!['ArrowLeft','ArrowRight'].includes(event.key)) return;
      event.preventDefault(); const tabs=[...document.querySelectorAll('[data-panel]')];
      const index=(tabs.indexOf(button)+(event.key === 'ArrowRight' ? 1 : -1)+tabs.length)%tabs.length;
      selectPanel(tabs[index].dataset.panel); tabs[index].focus();
    });
  }
  $('new-conversation').addEventListener('click',resetConversation);
  $('refresh-status').addEventListener('click',refreshHealth);
  $('stop-waiting').addEventListener('click',() => state.controller?.abort());
  $('library-button').addEventListener('click',() => $('library-dialog').showModal());
  $('audit-button').addEventListener('click',() => $('quotation-dialog').showModal());
  $('quotation-form').addEventListener('submit',submitQuotation);
  for (const button of document.querySelectorAll('[data-close-dialog]')) button.addEventListener('click',() => $(button.dataset.closeDialog).close());
  for (const dialog of document.querySelectorAll('dialog')) dialog.addEventListener('click',event => {
    if (event.target !== dialog) return;
    const bounds=dialog.getBoundingClientRect();
    if (event.clientX<bounds.left || event.clientX>bounds.right || event.clientY<bounds.top || event.clientY>bounds.bottom) dialog.close();
  });
  let previous=null; try {previous=localStorage.getItem(storageKey);} catch (_) {}
  setSession(previous); Promise.allSettled([refreshHealth(),loadLibrary(),loadHistory()]);
})();
