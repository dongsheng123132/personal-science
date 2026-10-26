import fs from 'node:fs';
import path from 'node:path';
import { marked } from 'marked';
const root=path.resolve(import.meta.dirname,'..'), out=path.join(import.meta.dirname,'dist');
fs.mkdirSync(out,{recursive:true});
const repo='https://github.com/dongsheng123132/personal-science';
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const read=p=>fs.readFileSync(path.join(root,p),'utf8');
const files=fs.readdirSync(path.join(root,'experiments')).filter(n=>n.endsWith('.md')&&!n.startsWith('_'));
const docs={'MANIFESTO.md':'manifesto','CHARTER.md':'charter','CONTRIBUTING.md':'contribute','RESULTS.md':'results','inbox/candidates.md':'candidates','README.md':'experiments'};
function link(href,source){
 if(/^https?:\/\//i.test(href)||href.startsWith('#'))return href;
 if(/^[a-z][a-z0-9+.-]*:/i.test(href))return '#';
 const [p,hash]=href.split('#'), resolved=path.posix.normalize(path.posix.join(path.posix.dirname(source),p));
 let target=docs[resolved]?`/${docs[resolved]}/`:resolved.startsWith('experiments/')&&!path.posix.basename(resolved).startsWith('_')?`/experiments/${path.posix.basename(resolved,'.md')}/`:resolved.startsWith('inbox/designs/')?'/drafts/':`${repo}/blob/main/${resolved}`;
 return target+(hash?'#'+hash:'');
}
function markdown(text,source){
 // Never pass raw HTML from AI/source markdown into the website.
 const renderer=new marked.Renderer();
 renderer.html=({text})=>esc(text);
 renderer.link=({href,text})=>`<a href="${esc(link(href,source))}">${esc(text)}</a>`;
 renderer.image=({text})=>`<span>${esc(text)}</span>`;
 return marked.parse(text.replace(/<!--[\s\S]*?-->/g,''),{renderer});
}
const nav=[['/experiments/','实验清单'],['/candidates/','每日发现'],['/drafts/','AI 草稿'],['/manifesto/','宣言'],['/contribute/','参与贡献']];
function page(url,title,body){const dir=path.join(out,url);fs.mkdirSync(dir,{recursive:true});fs.writeFileSync(path.join(dir,'index.html'),`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="用身边的工具和 AI，开始你的第一个科学实验。Personal Science 个人科学实验清单。"><title>${esc(title)} · Personal Science</title><link rel="stylesheet" href="/style.css"></head><body><header><a class="brand" href="/">Personal Science<span>个人科学</span></a><nav>${nav.map(([u,t])=>`<a href="${u}" ${url===u.slice(1)?'aria-current="page"':''}>${t}</a>`).join('')}</nav><a class="github" href="${repo}">GitHub ↗</a></header><main>${body}</main><footer><div><b>一个人，也可以开始探索。</b><p>提出问题 · 动手测量 · 让 AI 帮你分析 · 分享结果</p></div><div><a href="/charter/">章程</a> · <a href="/results/">实验记录</a> · <a href="${repo}/blob/main/README.en.md">English</a><p>内容 CC0 · 实验方案不等于实测验证</p></div></footer></body></html>`);}
const entries=files.map(file=>{const text=read('experiments/'+file);const field=n=>(text.match(new RegExp('\\| \\*\\*'+n+'\\*\\* \\| (.*?) \\|'))||[])[1]||'见实验页';return {file,text,title:text.split('\n')[0].replace(/^# /,''),intro:(text.match(/^> (.+)$/m)||[])[1]||'',cost:field('花费'),time:field('时间'),slug:file.slice(0,-3)};});
const card=e=>`<a class="card" href="/experiments/${e.slug}/"><div class="meta">${esc(e.time)} <span>${esc(e.cost)}</span></div><h3>${esc(e.title)}</h3><p>${esc(e.intro)}</p><strong>看看怎么做 →</strong></a>`;
const picks=['blind-cola','galileo-inclined-plane','polarization-tape','eratosthenes'].map(s=>entries.find(e=>e.slug===s)).filter(Boolean);
page('','把好奇心变成实验',`<section class="hero"><div class="eyebrow">PERSONAL SCIENCE / 科研平权</div><h1>别只问为什么。<br>亲手试一试。</h1><p>可乐真的喝得出区别吗？光能被一根头发挡出条纹吗？<br>用身边的工具提出问题，让 AI 帮你设计、记录和分析。</p><div class="actions"><a class="button" href="/experiments/">找一个实验开始 →</a><a class="secondary" href="/contribute/">贡献你的好奇心</a></div><div class="stats"><span><b>${entries.length}</b> 份实验方案</span><span>年代不限，兴趣优先</span><span>手机 · AI · ESP32</span></div></section><section><div class="section-title"><h2>从一个小问题开始</h2><a href="/experiments/">查看全部 →</a></div><div class="grid">${picks.map(card).join('')}</div></section><section class="strip"><div><small>AI 在这里做什么？</small><h2>让一个人的想法，<br>多几双帮忙的手。</h2></div><div><p><b>动手前</b>　比较实验方案，梳理变量，估算需要的量程。</p><p><b>动手后</b>　从视频提取数据，写分析脚本，画图和检查误差。</p><p><b>有了结果</b>　追问还有什么解释，再设计下一次实验。</p><a href="/drafts/">看看 AI 正在设计什么 →</a></div></section><section><h2>科学的入口，可以是一张桌子。</h2><p class="lead">给好奇的上班族、老师、学生、产品经理，也给每一个想亲手验证想法的人。经典实验和生活里的小问题，都值得重新做一次。</p><div class="actions"><a class="button" href="${repo}/issues/new/choose">提一个实验点子</a><a class="secondary" href="${repo}">Star / Fork / 提 PR ↗</a></div></section>`);
page('experiments/','实验清单',`<div class="eyebrow">EXPLORE</div><h1>今天想验证什么？</h1><p class="lead">${entries.length} 份方案。从你手边的材料开始。预算和时间是参考，动手前请先读器材、方法与安全说明。</p><label class="search">搜索实验 <input id="search" type="search" placeholder="试试：手机、光、电池、植物…"></label><div class="grid" id="cards">${entries.map(card).join('')}</div><p id="empty" hidden>没有匹配的实验。换个词试试，或去 GitHub 提个新点子。</p><script>document.querySelector('#search').oninput=e=>{let count=0;document.querySelectorAll('#cards .card').forEach(c=>{c.hidden=!c.textContent.toLowerCase().includes(e.target.value.toLowerCase());if(!c.hidden)count++});document.querySelector('#empty').hidden=count>0}</script>`);
for(const e of entries)page(`experiments/${e.slug}/`,e.title,`<div class="breadcrumbs"><a href="/experiments/">← 全部实验</a></div><div class="notice">这是实验方案，尚不代表经过实测验证。请先阅读安全说明；保留原始数据，AI 的分析也需要核对。</div><article>${markdown(e.text,'experiments/'+e.file)}</article><div class="actions"><a class="button" href="${repo}/edit/main/experiments/${e.file}">改进这份方案 ↗</a><a href="/results/">分享你的实验结果 →</a></div>`);
for(const [src,slug] of Object.entries(docs)){if(src==='README.md')continue;if(!fs.existsSync(path.join(root,src)))continue;page(slug+'/',{'manifesto':'我们的宣言','charter':'项目章程','contribute':'参与贡献','results':'实验记录','candidates':'每日发现'}[slug],`<div class="eyebrow">PERSONAL SCIENCE</div>${slug==='candidates'?'<div class="notice">AI 筛选的候选，仅供发现灵感；不是已经核实的实验方案。</div>':''}<article>${markdown(read(src),src)}</article>`);}
const drafts=fs.readdirSync(path.join(root,'inbox/designs')).filter(n=>n.endsWith('.md')&&n!=='README.md').sort().reverse();
page('drafts/','AI 实验草稿',`<div class="eyebrow">IDEAS IN PROGRESS</div><h1>下一个实验，从这里长出来。</h1><p class="lead">AI 自动提出方案，人来检查、尝试和改进。这里的草稿可能存在公式、器材或安全问题，不能直接当操作指南。</p><div class="grid">${drafts.map((f,i)=>`<a class="card" href="/drafts/${i}/"><div class="meta">待核对 · AI 草稿</div><h3>${esc(f.replace(/\.md$/,''))}</h3><strong>阅读与改进 →</strong></a>`).join('')}</div>`);
for(const [i,f] of drafts.entries())page(`drafts/${i}/`,f.replace(/\.md$/,''),`<a href="/drafts/">← 返回草稿列表</a><div class="notice">AI 草稿 · 未经人工核对。不要照此直接操作。欢迎核对来源、指出问题，再通过 PR 完善。</div><article>${markdown(read('inbox/designs/'+f),'inbox/designs/'+f)}</article><a class="button" href="${repo}/blob/main/inbox/designs/${encodeURIComponent(f)}">在 GitHub 查看与贡献 ↗</a>`);
fs.copyFileSync(path.join(import.meta.dirname,'style.css'),path.join(out,'style.css'));
console.log(`Built ${entries.length} experiment pages, ${drafts.length} drafts and site navigation.`);
