import fs from 'node:fs';
import path from 'node:path';
import { marked } from 'marked';
import { referencePages } from './references.mjs';
const root=path.resolve(import.meta.dirname,'..'), out=path.join(import.meta.dirname,'dist');
fs.rmSync(out,{recursive:true,force:true});fs.mkdirSync(out,{recursive:true});
const repo='https://github.com/dongsheng123132/personal-science';
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const read=p=>fs.readFileSync(path.join(root,p),'utf8');
const ls=d=>{try{return fs.readdirSync(path.join(root,d))}catch(e){return[]}};
const readJSON=p=>{try{return JSON.parse(read(p))}catch(e){return null}};
const files=fs.readdirSync(path.join(root,'experiments')).filter(n=>n.endsWith('.md')&&!n.startsWith('_'));
const docs={'MANIFESTO.md':'manifesto','CHARTER.md':'charter','CONTRIBUTING.md':'contribute','RESULTS.md':'results','inbox/candidates.md':'candidates','RULES.md':'rules','README.md':'experiments'};
const enDocs={'MANIFESTO.en.md':'en/manifesto','CHARTER.en.md':'en/charter','CONTRIBUTING.en.md':'en/contribute','README.en.md':'en'};
function link(href,source,lang){
 if(/^https?:\/\//i.test(href)||href.startsWith('#'))return href;
 if(/^[a-z][a-z0-9+.-]*:/i.test(href))return '#';
 const [p,hash]=href.split('#'), resolved=path.posix.normalize(path.posix.join(path.posix.dirname(source),p));
 let target=lang==='en'&&enDocs[resolved]?`/${enDocs[resolved]}/`:docs[resolved]?`/${docs[resolved]}/`:resolved.startsWith('experiments/')&&!path.posix.basename(resolved).startsWith('_')?`/experiments/${path.posix.basename(resolved,'.md')}/`:resolved.startsWith('inbox/designs/')?'/drafts/':`${repo}/blob/main/${resolved}`;
 return target+(hash?'#'+hash:'');
}
function markdown(text,source,lang){
 const renderer=new marked.Renderer();
 renderer.html=({text})=>esc(text);
 renderer.link=({href,text})=>`<a href="${esc(link(href,source,lang))}">${esc(text)}</a>`;
 renderer.image=({text})=>`<span>${esc(text)}</span>`;
 return marked.parse(text.replace(/<!--[\s\S]*?-->/g,''),{renderer});
}
const nav=[['/sources/','参考资料'],['/experiments/','实验清单'],['/daily/','每日候选'],['/rules/','规则'],['/drafts/','AI 草稿'],['/review/','风险公示'],['/manifesto/','宣言'],['/contribute/','参与贡献']];
const navEn=[['/en/experiments/','Experiments'],['/en/manifesto/','Manifesto'],['/en/contribute/','Contribute'],['/en/charter/','Charter']];
function page(url,title,body,lang){const en=lang==='en';const dir=path.join(out,url);fs.mkdirSync(dir,{recursive:true});fs.writeFileSync(path.join(dir,'index.html'),`<!doctype html><html lang="${en?'en':'zh-CN'}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="${en?'Run real science experiments with everyday tools and AI. Personal Science — a list of experiments you can do at home.':'用身边的工具和 AI，开始你的第一个科学实验。Personal Science 个人科学实验清单。'}"><title>${esc(title)} · Personal Science</title><link rel="stylesheet" href="/style.css"></head><body><header><a class="brand" href="${en?'/en/':'/'}">Personal Science<span>${en?'one person = one lab':'个人科学'}</span></a><nav>${(en?navEn:nav).map(([u,t])=>`<a href="${u}" ${url===u.slice(1)?'aria-current="page"':''}>${t}</a>`).join('')}</nav><a class="lang-switch" href="${en?'/':'/en/'}" hreflang="${en?'zh-CN':'en'}">${en?'中文':'English'}</a><a class="github" href="${repo}">GitHub ↗</a></header><main>${body}</main><footer><div><b>${en?'One person can start exploring.':'一个人，也可以开始探索。'}</b><p>${en?'Ask a question · Measure it yourself · Let AI help analyze · Share the result':'提出问题 · 动手测量 · 让 AI 帮你分析 · 分享结果'}</p></div><div>${en?`<a href="/en/charter/">Charter</a> · <a href="/en/manifesto/">Manifesto</a> · <a href="/en/contribute/">Contribute</a> · <a href="/" hreflang="zh-CN">中文</a><p>Content CC0 · A plan is not a verified result</p>`:`<a href="/charter/">章程</a> · <a href="/results/">实验记录</a> · <a href="/en/" hreflang="en">English</a><p>内容 CC0 · 实验方案不等于实测验证</p>`}</div></footer></body></html>`);}
const entries=files.map(file=>{const text=read('experiments/'+file);const field=n=>(text.match(new RegExp('\\| \\*\\*'+n+'\\*\\* \\| (.*?) \\|'))||[])[1]||'见实验页';return {file,text,title:text.split('\n')[0].replace(/^# /,''),intro:(text.match(/^> (.+)$/m)||[])[1]||'',cost:field('花费'),time:field('时间'),slug:file.slice(0,-3)};});
const card=e=>`<a class="card" href="/experiments/${e.slug}/"><div class="meta">${esc(e.time)} <span>${esc(e.cost)}</span></div><h3>${esc(e.title)}</h3><p>${esc(e.intro)}</p><strong>看看怎么做 →</strong></a>`;
const picks=['blind-cola','galileo-inclined-plane','polarization-tape','eratosthenes'].map(s=>entries.find(e=>e.slug===s)).filter(Boolean);

// ---- 每日归档（feed/archive/*.json + inbox/candidates-archive/*.md）----
const drafts=ls('inbox/designs').filter(n=>n.endsWith('.md')&&n!=='README.md').sort().reverse();
const draftDate=f=>(f.match(/^(\d{4}-\d{2}-\d{2})/)||[])[1]||'';
const latestDraft=drafts[0]||'', latestDraftDate=draftDate(latestDraft);
const draftCount=drafts.filter(f=>draftDate(f)===latestDraftDate).length;
const isWikiJunk=it=>/wiki/i.test(String(it.source||''))&&!it.title_signal&&!(it.obj_hits||[]).length&&!(it.per_hits||[]).length&&!(it.modern_hits||[]).length;
const feedArch=ls('feed/archive').filter(n=>/^\d{4}-\d{2}-\d{2}\.json$/.test(n)).map(n=>{const j=readJSON('feed/archive/'+n)||{};const items=(j.items||[]).filter(it=>it&&it.title&&!isWikiJunk(it));return{date:n.slice(0,10),count:items.length,items};}).sort((a,b)=>b.date.localeCompare(a.date));
const candArch=ls('inbox/candidates-archive').filter(n=>/^\d{4}-\d{2}-\d{2}\.md$/.test(n)).map(n=>({date:n.slice(0,10),text:read('inbox/candidates-archive/'+n)})).sort((a,b)=>b.date.localeCompare(a.date));
const feedMap=new Map(feedArch.map(x=>[x.date,x])), candMap=new Map(candArch.map(x=>[x.date,x]));
const allDates=[...new Set([...feedArch.map(x=>x.date),...candArch.map(x=>x.date)])].sort((a,b)=>b.localeCompare(a));
const reviews=ls('reviews').filter(n=>n.endsWith('.json')).map(n=>readJSON('reviews/'+n)).filter(Boolean).sort((a,b)=>String(b.date).localeCompare(String(a.date)));
const RISK_ZH={high:'高风险 · 已拦下',medium:'中风险 · 待人工',low:'低风险'};
const statusZh=(r)=>({published:'已发布',held:'未通过自动发布，等人工处理',rejected:'已否决',retracted:'已撤回'}[r.status]||r.status||'');
const humanMark=(r)=>r.human_reviewed?'<span class="humanbadge">人工复核 · 仅供参考，不作为正式推荐</span>':'';
const countH3=md=>(md.match(/^### /gm)||[]).length;
const candCount=md=>{const m=md.match(/筛出\s*\**\s*(\d+)\s*条/);return m?+m[1]:countH3(md)};
const latest=readJSON('feed/latest.json')||{date:'',count:0,items:[]};
const todayFeed=feedMap.get(latest.date), todayCand=candMap.get(latest.date);
const todayFeedN=todayFeed?todayFeed.count:(latest.count||0), todayCandN=todayCand?candCount(todayCand.text):0;
const todayItems=((todayFeed?todayFeed.items:latest.items)||[]).slice(0,3);
const todayStrip=`<section class="strip today"><div><small>今日更新 · ${esc(latest.date)}</small><h2>今天抓到 ${todayFeedN} 条新发现、AI 筛出 ${todayCandN} 条候选，产出 ${draftCount} 份 AI 草稿。</h2><p class="lead" style="font-size:15px;margin:12px 0 0">每天 06:17，机器人在网上找「一个人在家能重做的实验」，AI 再按章程筛一遍。</p></div><div>${todayItems.length?`<ul class="tinylist">${todayItems.map(i=>`<li><a href="${esc(i.url)}" target="_blank" rel="noopener noreferrer">${esc(i.title)}</a> <span class="meta">${esc(i.source||'')}</span></li>`).join('')}</ul>`:''}<p><a href="/daily/">看每一天 →</a> · <a href="/drafts/">AI 草稿 →</a> · <a href="/candidates/">今天的候选 →</a></p></div></section>`;

page('','把好奇心变成实验',`<section class="hero"><div class="eyebrow">PERSONAL SCIENCE / 科研平权</div><h1>别只问为什么。<br>亲手试一试。</h1><p>可乐真的喝得出区别吗？光能被一根头发挡出条纹吗？<br>用身边的工具提出问题，让 AI 帮你设计、记录和分析。</p><div class="actions"><a class="button" href="/experiments/">找一个实验开始 →</a><a class="secondary" href="/contribute/">贡献你的好奇心</a></div><div class="stats"><span><b>${entries.length}</b> 份实验方案</span><span>年代不限，兴趣优先</span><span>手机 · AI · ESP32</span></div></section>${todayStrip}<section><div class="section-title"><h2>从一个小问题开始</h2><a href="/experiments/">查看全部 →</a></div><div class="grid">${picks.map(card).join('')}</div></section><section class="strip"><div><small>AI 在这里做什么？</small><h2>让一个人的想法，<br>多几双帮忙的手。</h2></div><div><p><b>动手前</b>　比较实验方案，梳理变量，估算需要的量程。</p><p><b>动手后</b>　从视频提取数据，写分析脚本，画图和检查误差。</p><p><b>有了结果</b>　追问还有什么解释，再设计下一次实验。</p><a href="/drafts/">看看 AI 正在设计什么 →</a></div></section><section><h2>科学的入口，可以是一张桌子。</h2><p class="lead">给好奇的上班族、老师、学生、产品经理，也给每一个想亲手验证想法的人。经典实验和生活里的小问题，都值得重新做一次。</p><div class="actions"><a class="button" href="${repo}/issues/new/choose">提一个实验点子</a><a class="secondary" href="${repo}">Star / Fork / 提 PR ↗</a></div></section>`);
page('experiments/','实验清单',`<div class="eyebrow">EXPLORE</div><h1>今天想验证什么？</h1><p class="lead">${entries.length} 份方案。从你手边的材料开始。预算和时间是参考，动手前请先读器材、方法与安全说明。</p><label class="search">搜索实验 <input id="search" type="search" placeholder="试试：手机、光、电池、植物…"></label><div class="grid" id="cards">${entries.map(card).join('')}</div><p id="empty" hidden>没有匹配的实验。换个词试试，或去 GitHub 提个新点子。</p><script>document.querySelector('#search').oninput=e=>{let count=0;document.querySelectorAll('#cards .card').forEach(c=>{c.hidden=!c.textContent.toLowerCase().includes(e.target.value.toLowerCase());if(!c.hidden)count++});document.querySelector('#empty').hidden=count>0}</script>`);
const reviewByTarget=new Map(reviews.filter(r=>r.target).map(r=>[r.target,r]));
for(const e of entries){const rv=reviewByTarget.get('experiments/'+e.file);const rbanner=rv?`<div class="notice riskbanner risk-${esc(rv.risk&&rv.risk.level||'low')}"><b>风险提示</b>：这一页经过复核，判定为「${esc(RISK_ZH[(rv.risk&&rv.risk.level)||'low']||'')}」。${esc((rv.risk&&rv.risk.summary)||'').slice(0,180)} <a href="/review/${esc(rv.slug)}/">看完整评审 →</a></div>`:'';
page(`experiments/${e.slug}/`,e.title,`<div class="breadcrumbs"><a href="/experiments/">← 全部实验</a></div>${rbanner}<div class="notice">这是实验方案，尚不代表经过实测验证。请先阅读安全说明；保留原始数据，AI 的分析也需要核对。</div><article>${markdown(e.text,'experiments/'+e.file)}</article><div class="actions"><a class="button" href="${repo}/edit/main/experiments/${e.file}">改进这份方案 ↗</a><a href="/results/">分享你的实验结果 →</a></div>`);}
for(const [src,slug] of Object.entries(docs)){if(src==='README.md')continue;if(!fs.existsSync(path.join(root,src)))continue;page(slug+'/',{'manifesto':'我们的宣言','charter':'项目章程','contribute':'参与贡献','results':'实验记录','candidates':'每日发现','rules':'挑选规则'}[slug],`<div class="eyebrow">PERSONAL SCIENCE</div>${slug==='candidates'?'<div class="notice">AI 筛选的候选，仅供发现灵感；不是已经核实的实验方案。下面是今天的清单，历史清单见 <a href="/daily/">每日候选</a>。</div>':''}<article>${markdown(read(src),src)}</article>`);}

// ---- 每日候选：索引 + 按天页面 ----
page('daily/','每日候选 · 按天看',`<div class="eyebrow">DAILY</div><h1>每天，AI 都在找新问题。</h1><p class="lead">共 ${allDates.length} 天。机器人在哪一天看到什么、AI 觉得哪几条值得做，都按天留着——这是一条能往回翻的「好奇心流水账」。</p><div class="daylist">${allDates.map((d,idx)=>{const f=feedMap.get(d),c=candMap.get(d);const fc=f?f.count:0,cc=c?candCount(c.text):0;const meta=[cc?`${cc} 条候选`:'',fc?`${fc} 条新发现`:''].filter(Boolean).join(' · ');const top=(f&&f.items&&f.items[0])?`<em>${esc(f.items[0].title)}</em>`:'';return `<a class="dayrow${idx===0?' latest':''}" href="/daily/${d}/"><b>${d}</b><span class="meta">${meta||'暂无新发现'}</span><span class="daytop">${top}</span><span class="go">→</span></a>`}).join('')}</div>`);
for(const d of allDates){const f=feedMap.get(d),c=candMap.get(d);const i=allDates.indexOf(d);const prev=allDates[i+1],next=allDates[i-1];
 const candBody=c?`<article>${markdown(c.text.replace(/^# .*\n+/,''),'inbox/candidates-archive/'+d+'.md')}</article>`:'';
 const rawBody=f&&f.items.length?`<h2>那天的原始发现 <small style="font-weight:400">${f.count} 条</small></h2><ul class="rawlist">${f.items.map(it=>`<li><a href="${esc(it.url)}" target="_blank" rel="noopener noreferrer">${esc(it.title)}</a><span class="meta">${esc(it.source||'')}${it.published?' · '+esc(it.published):''}${it.score?' · '+esc(String(it.score))+' 分':''}</span>${it.summary?`<p>${esc(it.summary)}</p>`:''}${it.why?`<p class="why">▸ ${esc(it.why)}</p>`:''}</li>`).join('')}</ul>`:'';
 page(`daily/${d}/`,`${d} 的候选`,`<div class="breadcrumbs"><a href="/daily/">← 每日候选</a></div><h1>${d}</h1><p class="lead">那天机器人抓到 ${f?f.count:0} 条新发现，AI 从候选池里筛出 ${c?candCount(c.text):0} 条候选。</p>${candBody}${rawBody}<p><a href="/pool/${d}/">看那天完整的候选池（含没入选的）→</a></p><div class="actions">${prev?`<a class="secondary" href="/daily/${prev}/">← ${prev}</a>`:''}${next?`<a class="secondary" href="/daily/${next}/">${next} →</a>`:''}</div>`);}


// ---- 候选池：全部公开（含没入选的）+ 每条的信号 ----
const poolArch=ls('feed/pool-archive').filter(n=>/^\d{4}-\d{2}-\d{2}\.json$/.test(n)).map(n=>{const j=readJSON('feed/pool-archive/'+n)||{};const items=j.items||[];return{date:n.slice(0,10),count:j.count??items.length,items};}).sort((a,b)=>b.date.localeCompare(a.date));
if(poolArch.length){
 page('pool/','候选池 · 全公开',`<div class="eyebrow">POOL</div><h1>机器人每天捞到什么，全部摆出来。</h1><p class="lead">这里不做二次筛选——<b>每一条都列出分数、命中的关键词、以及最后有没有入选</b>。没入选不是"不存在"，只是没排上。规则见 <a href="/rules/">挑选规则</a>。</p><div class="daylist">${poolArch.map(x=>`<a class="dayrow" href="/pool/${x.date}/"><b>${x.date}</b><span class="meta">${x.count} 条候选</span><span class="daytop"></span><span class="go">→</span></a>`).join('')}</div>`);
 for(const x of poolArch){
  const c=candMap.get(x.date);
  const picked=new Set();
  if(c){for(const m of c.text.matchAll(/原标题：(.+)/g)) picked.add(m[1].trim());}
  const rows=x.items.map(it=>{
    const hit=((it.obj_hits||[]).concat(it.per_hits||[],it.modern_hits||[])).slice(0,6).join('、')||'—';
    const sel=picked.has(String(it.title||'').trim());
    return `<tr><td>${it.url?`<a href="${esc(it.url)}" target="_blank" rel="noopener noreferrer">${esc(it.title||'')}</a>`:esc(it.title||'')}</td><td class="meta">${esc(it.source||'')}</td><td>${esc(String(it.score??''))}</td><td class="meta">${esc(hit)}</td><td>${sel?'<b class="ok">入选</b>':'<span class="no">未入选</span>'}</td></tr>`;
  }).join('');
  page(`pool/${x.date}/`,`${x.date} 的候选池`,`<div class="breadcrumbs"><a href="/pool/">← 候选池</a></div><h1>${x.date} · 全部候选</h1><p class="lead">共 ${x.count} 条。命中"入选"的进了当天的 AI 候选清单，其余原样保留。<a href="/daily/${x.date}/">看那天的筛选结果 →</a></p><div class="tablewrap"><table class="pooltable"><thead><tr><th>标题</th><th>来源</th><th>分</th><th>命中词</th><th>结果</th></tr></thead><tbody>${rows}</tbody></table></div>`);
 }
}

page('drafts/','AI 实验草稿',`<div class="eyebrow">IDEAS IN PROGRESS</div><h1>下一个实验，从这里长出来。</h1><p class="lead">AI 自动提出方案，人来检查、尝试和改进。这里的草稿可能存在公式、器材或安全问题，不能直接当操作指南。</p><div class="grid">${drafts.map((f,i)=>`<a class="card" href="/drafts/${i}/"><div class="meta">待核对 · AI 草稿 · ${esc(f.slice(0,10))}</div><h3>${esc(f.replace(/\.md$/,''))}</h3><strong>阅读与改进 →</strong></a>`).join('')}</div>`);
for(const [i,f] of drafts.entries())page(`drafts/${i}/`,f.replace(/\.md$/,''),`<a href="/drafts/">← 返回草稿列表</a><div class="notice">AI 草稿 · 未经人工核对。不要照此直接操作。欢迎核对来源、指出问题，再通过 PR 完善。</div><article>${markdown(read('inbox/designs/'+f),'inbox/designs/'+f)}</article><a class="button" href="${repo}/blob/main/inbox/designs/${encodeURIComponent(f)}">在 GitHub 查看与贡献 ↗</a>`);

// ---- 风险公示：没通过自动发布的草稿也公开，标注风险 + 权威入口 ----
const fsev=s=>({critical:'必须拦',warn:'要人看',info:'提示'}[s]||s);
{
 const reviewList = reviews.length ? '<div class="grid">'+reviews.map(r=>`<a class="card" href="/review/${r.slug}/"><div class="meta">${esc(r.date)} · ${esc(r.category||'')}</div><h3>${esc(r.title)}</h3><p>${esc(r.oneline||'')}</p><div class="riskline risk-${esc(r.risk&&r.risk.level||'low')}">${esc(RISK_ZH[(r.risk&&r.risk.level)||'low']||'')} · ${esc(statusZh(r))}</div><strong>看评审与来源 →</strong></a>`).join('')+'</div>' : '<p class="notice">还没有评审记录。自动转正每天跑一次，被拦下的草稿会出现在这里。</p>';
 page('review/','风险公示',`<div class="eyebrow">REVIEW</div><h1>没过关的，也摆出来。</h1><p class="lead">这些是 AI 写、AI 审的草稿。有的被独立评审拦下了。拦住不等于没价值——这里写清楚：<b>风险是什么</b>、<b>依据在哪</b>、<b>它为什么仍然值得看</b>。欢迎接手改进。</p>${reviewList}`);
 for(const r of reviews){
  const srcs=(r.sources||[]).map(x=>`<li><a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">${esc(x.label)}</a></li>`).join('');
  const fnd=((r.risk&&r.risk.findings)||[]).map(f=>`<li class="sev-${esc(f.severity||'info')}"><b>[${esc(fsev(f.severity))}]</b> ${esc(f.what||'')}${f.where?` <span class="meta">（${esc(f.where)}）</span>`:''}</li>`).join('');
  page(`review/${r.slug}/`,r.title,`<div class="breadcrumbs"><a href="/review/">← 风险公示</a></div><h1>${esc(r.title)}</h1><p class="lead">${esc(r.oneline||'')}</p>${r.status==='retracted'?'<div class="notice" style="border-color:#b91c1c;background:#fef2f2"><b>已撤回</b>：这一份在后来的复核里被判定不该发布，内容仅作历史记录保留。</div>':''}${humanMark(r)}<div class="riskbox risk-${esc((r.risk&&r.risk.level)||'low')}"><b>${esc(RISK_ZH[(r.risk&&r.risk.level)||'low']||'')}</b> · ${esc(statusZh(r))}${r.risk&&r.risk.summary?`<p>${esc(r.risk.summary)}</p>`:''}</div><h2>权威入口（可点开核对）</h2><ul class="srclist">${srcs||'<li>（暂无）</li>'}</ul><h2>评审发现了什么</h2><ul class="findings">${fnd||'<li>（无）</li>'}</ul><h2>它为什么仍然值得看</h2><p>${esc((r.curation&&r.curation.why)||'')}</p><h2>状态与参与方式</h2><p>${esc(statusZh(r))}。${r.pr?`这份草稿的改造正在 <a href="${esc(r.pr)}">PR</a> 里进行，欢迎接手、指正、补实验数据。`:'欢迎在 GitHub 上接着改。'}</p><div class="actions">${r.pr?`<a class="button" href="${esc(r.pr)}">看 PR / 参与改进 ↗</a>`:''}<a class="secondary" href="${repo}">去仓库 ↗</a></div>`);
 }
}

referencePages(page,esc);
fs.copyFileSync(path.join(import.meta.dirname,'style.css'),path.join(out,'style.css'));

// --- English section (/en/) ---
page('en/','Personal Science — one person = one lab',`<section class="hero"><div class="eyebrow">PERSONAL SCIENCE / SCIENCE EQUITY</div><h1>Don't just ask why.<br>Try it yourself.</h1><p>Can you actually tell Coke from Pepsi? Can a strand of hair split light into stripes?<br>Ask questions with everyday tools, and let AI help you design, record and analyze.</p><div class="actions"><a class="button" href="/en/experiments/">Find an experiment →</a><a class="secondary" href="/en/contribute/">Contribute your curiosity</a></div><div class="stats"><span><b>${entries.length}</b> experiment plans</span><span>No gatekeeping, curiosity first</span><span>Phone · AI · ESP32</span></div></section><div class="notice">Experiment detail pages are currently written in Chinese. Translations are very welcome — one page = one PR.</div><article>${markdown(read('README.en.md'),'README.en.md','en')}</article>`,'en');
page('en/experiments/','Experiments',`<div class="eyebrow">EXPLORE</div><h1>What do you want to verify today?</h1><p class="lead">${entries.length} plans, starting from what you already have. Budget and time are estimates — read the materials, method and safety sections before you start.</p><label class="search">Search experiments <input id="search" type="search" placeholder="Try: phone, light, battery, plant…"></label><div class="grid" id="cards">${entries.map(card).join('')}</div><p id="empty" hidden>No matching experiment. Try another word, or propose a new idea on GitHub.</p><script>document.querySelector('#search').oninput=e=>{let count=0;document.querySelectorAll('#cards .card').forEach(c=>{c.hidden=!c.textContent.toLowerCase().includes(e.target.value.toLowerCase());if(!c.hidden)count++});document.querySelector('#empty').hidden=count>0}</script><div class="notice">Cards above link to the Chinese experiment pages; English translations of detail pages are not available yet.</div>`,'en');
for(const [src,slug] of Object.entries(enDocs)){if(src==='README.en.md')continue;if(!fs.existsSync(path.join(root,src)))continue;page(slug+'/',{'en/manifesto':'Manifesto','en/charter':'Charter','en/contribute':'Contribute'}[slug],`<div class="eyebrow">PERSONAL SCIENCE</div><article>${markdown(read(src),src,'en')}</article>`,'en');}
console.log(`Built ${entries.length} experiments, ${drafts.length} drafts, ${allDates.length} daily pages, ${allDates.length} feeds.`);
