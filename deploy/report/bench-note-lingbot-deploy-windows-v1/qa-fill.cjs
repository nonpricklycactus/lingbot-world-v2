const fs=require('fs'),path=require('path');
const root=path.resolve(__dirname,'../../..');
const tools=path.join(root,'tools/benchnote/lib');
const {mdToBlocks}=require(path.join(tools,'blocks.cjs'));
const {parseFrontMatter,stripFrontMatter,resolveTheme}=require(path.join(tools,'profile.cjs'));
const {pageHtml}=require(path.join(tools,'theme.cjs'));
const {resolveBrowser,resolvePlaywright}=require(path.join(tools,'env.cjs'));
const {chromium}=require(resolvePlaywright());
(async()=>{
const source=path.join(__dirname,'../bench-note-lingbot-deploy-windows-v1.zh.md');
const md=fs.readFileSync(source,'utf8'),theme=resolveTheme({frontMatter:parseFrontMatter(md).data});
const blocks=mdToBlocks(stripFrontMatter(md),root).filter(b=>!b.includes('class="pagemark"'));
const plan=JSON.parse(fs.readFileSync(path.join(__dirname,'page-plan.json'),'utf8'));
const browser=await chromium.launch({executablePath:resolveBrowser(),headless:true});
const page=await browser.newPage({viewport:{width:1080,height:1440}});
for(let i=0;i<blocks.length;i++){
 await page.setContent(pageHtml({body:blocks[i],theme}),{waitUntil:'load'});
 await page.evaluate(async()=>{await document.fonts.ready;await Promise.all([...document.images].map(im=>im.decode()));});
 const m=await page.evaluate(()=>{
   const main=document.querySelector('main'),outer=main.firstElementChild,panel=outer.querySelector('.report-panel')||outer;
   const cs=getComputedStyle(panel);const gap=parseFloat(cs.rowGap||cs.gap||0);
   const kids=[...panel.children].filter(e=>e.tagName!=='STYLE'&&getComputedStyle(e).display!=='none');
   let sum=0;for(const k of kids)sum+=k.getBoundingClientRect().height;
   sum+=gap*(kids.length-1);
   const padTop=parseFloat(cs.paddingTop),padBot=parseFloat(cs.paddingBottom);
   const inner=panel.getBoundingClientRect().height-padTop-padBot;
   return {content_px:Math.round(sum), inner_px:Math.round(inner), slack:Math.round(inner-sum), kids:kids.length};
 });
 console.log(String(i+1).padStart(2,'0'), plan.pages[i].title.slice(0,22).padEnd(24), JSON.stringify(m));
}
await browser.close();
})();
