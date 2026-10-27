import fs from 'node:fs';
export function referencePages(page,esc){
 const sources=JSON.parse(fs.readFileSync(new URL('./sources.json',import.meta.url),'utf8'));
 page('sources/','参考资料与制作案例',`<h1>有人做过，值得再试。</h1><p class="lead">几百年前的实验、家庭自制仪器、现代传感器项目，都可以成为下一道题。这里区分来源和我们的启发，不把外部案例当成本项目的实测。</p><div class="notice">本站原创内容按 CC0 声明开放；外链文章、图片和视频保留原作者的版权与许可。引用链接不代表已获得转载授权。</div><div class="grid">${sources.map(s=>`<section class="card"><div class="meta">${esc(s.kind)}</div><h3><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title)} ↗</a></h3><p><b>来源：</b>${esc(s.credit)}</p><p>${esc(s.note)}</p><p><b>核对状态：</b>${esc(s.check)}</p></section>`).join('')}</div><h2>帮一份实验补上出处</h2><p>请提供具体链接、作者或机构、哪一步参考了它、有没有实际制作记录。视频请附关键时间点；只找到搜索结果就明确注明待核对。</p><a class="button" href="https://github.com/dongsheng123132/personal-science/issues/new/choose">提交来源或制作案例</a>`);
}
