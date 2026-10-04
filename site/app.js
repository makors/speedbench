'use strict';
const $ = id => document.getElementById(id);
const names = {'browser-use':'Browser Use','jev-ultrafast':'Jev Ultrafast','fastbrowse':'fastbrowse'};
const fmt = n => n == null ? '—' : `${n.toFixed(2)}s`;
const escapeHtml = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let data, tasks, sort = 'task', ascending = true;
function renderRecords(){
  const query = $('search').value.toLowerCase();
  let rows = data.rows.filter(r => (!$('agent').value || r.agent === $('agent').value)
    && (!$('status').value || r.status === $('status').value)
    && `${r.task_id} ${r.category} ${tasks.get(r.task_id)?.goal || ''}`.toLowerCase().includes(query));
  rows.sort((a,b)=>{const direction=ascending?1:-1;
    if(sort==='time') return (a.seconds==null?1:b.seconds==null?-1:(a.seconds-b.seconds)*direction);
    return a.task_id.localeCompare(b.task_id)*direction || a.position-b.position;});
  $('result-count').textContent=`${rows.length} / ${data.rows.length} records`;
  $('records').innerHTML=rows.length?rows.map(r=>`<tr><td><span class="task-label">${escapeHtml(r.task_id)}</span><span class="task-category">${escapeHtml(r.category)} · Repeat ${r.repeat}</span></td><td>${escapeHtml(names[r.agent])}</td><td><span class="badge ${escapeHtml(r.status)}">${escapeHtml(r.status)}</span></td><td class="metric">${fmt(r.seconds)}</td><td><a href="${escapeHtml(r.artifact_url)}${r.attempted?'result.json':'preflight.json'}">${r.attempted?'Result':'Preflight'} ↗</a>${r.status==='passed'||r.status==='failed'?` · <a href="${escapeHtml(r.artifact_url)}page.json">DOM</a> · <a href="${escapeHtml(r.artifact_url)}final.png">PNG</a>`:''}</td></tr>`).join(''):'<tr><td colspan="5">No records match these filters.</td></tr>';
}
async function init(){
  const responses=await Promise.all([fetch('data.json'),fetch('tasks.json')]);
  if(responses.some(r=>!r.ok)) throw new Error('Recorded run unavailable');
  const [loaded,taskData]=await Promise.all(responses.map(r=>r.json()));
  data=loaded;tasks=new Map(taskData.tasks.map(t=>[t.id,t]));
  const attempted=data.rows.filter(r=>r.attempted).length;
  $('measured').textContent=attempted;
  $('notice').innerHTML=`<strong>${data.ranked?'MEASURED COHORT':attempted?'INCOMPLETE / NOT RANKED':'NOT MEASURED / NOT RANKED'}</strong><br>${escapeHtml(data.notice)}${!attempted?'<br>Provider credentials were unavailable. No agent timing, success rate, or winner is claimed.':''}`;
  $('summary').innerHTML=data.summaries.map(r=>`<tr><td class="agent-name"><span class="rank">${r.rank==null?'—':String(r.rank).padStart(2,'0')}</span>${escapeHtml(names[r.agent])}</td><td class="metric">${r.passed} / ${r.attempted}${r.unavailable?` <span class="muted">(${r.unavailable} unavailable)</span>`:''}</td><td class="metric">${r.success_rate==null?'—':`${(r.success_rate*100).toFixed(1)}%`}</td><td class="metric">${fmt(r.median_success_seconds)}</td><td class="metric">${fmt(r.p95_success_seconds)}</td><td class="metric">${fmt(r.penalized_mean_seconds)}</td></tr>`).join('');
  $('run-id').textContent=`Run: ${data.run_id}`;
  $('run-settings').textContent=`Seed ${data.manifest.seed} / ${data.manifest.repeats} repeat(s) / ${data.manifest.timeout_seconds}s cap`;
  $('task-catalog').innerHTML=taskData.tasks.map(t=>`<article><span class="eyebrow">${escapeHtml(t.id)} / ${escapeHtml(t.category)}</span><p>${escapeHtml(t.goal)}</p><a href="${escapeHtml(t.start_url)}" target="_blank" rel="noopener noreferrer">Start page ↗</a></article>`).join('');
  for(const id of ['search','agent','status'])$(id).addEventListener('input',renderRecords);
  for(const [id,value] of [['sort-task','task'],['sort-time','time']])$(id).addEventListener('click',()=>{ascending=sort===value?!ascending:true;sort=value;renderRecords();});
  renderRecords();
}
init().catch(error=>{$('notice').textContent=`Cannot load recorded data: ${error.message}. No results are displayed.`;});
