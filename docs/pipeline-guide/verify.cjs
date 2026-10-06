const { chromium } = require('playwright');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const assert = require('node:assert/strict');
(async () => {
  const out = fs.mkdtempSync(path.join(os.tmpdir(), 'pickage-explorer-'));
  const model = JSON.parse(fs.readFileSync(path.join(__dirname, 'map.json'),'utf8'));
  const browser = await chromium.launch({ executablePath: process.env.GUIDE_BROWSER || 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless:true });
  const results=[];
  try {
    const context=await browser.newContext({offline:true});
    const page=await context.newPage(); const errors=[], network=[];
    page.on('pageerror', e=>errors.push(e.message));
    page.on('request', r=>{if(/^https?:/.test(r.url()))network.push(r.url());});
    const url=pathToFileURL(path.join(__dirname,'index.html')).href;
    const settle=()=>page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    async function sizeCheck() {
      await settle();
      const m=await page.evaluate(()=>({width:innerWidth,body:document.documentElement.scrollWidth,
        map:document.querySelector('#nodes').scrollWidth,mapBox:document.querySelector('#nodes').clientWidth,
        paths:document.querySelectorAll('#connections > path').length,
        duplicates:[...document.querySelectorAll('[id]')].map(el=>el.id).filter((id,i,all)=>all.indexOf(id)!==i)}));
      assert(m.body<=m.width,`Document overflow ${JSON.stringify(m)}`);
      assert(m.map<=m.mapBox+1,`Map overflow ${JSON.stringify(m)}`);
      assert.deepEqual(m.duplicates,[]);return m;
    }
    for(const width of [375,768,1024,1440]) {
      await page.setViewportSize({width,height:1000});await page.goto(url);
      assert(await page.locator('#explorer').isVisible());assert(!(await page.locator('#reader').isVisible()));
      assert.equal(await page.locator('.flow-node').count(),6);
      const metrics=await sizeCheck();assert.equal(metrics.paths,5);
      await page.screenshot({path:path.join(out,`overview-${width}.png`)});
      await page.locator('[data-node="preprocess"]').click();
      assert.equal(await page.locator('.flow-node').count(),6);await sizeCheck();
      await page.locator('[data-node="pre-repository"]').click();
      assert.equal(await page.locator('.flow-node').count(),model.nodes['pre-repository'].children.length);
      await settle();await page.screenshot({path:path.join(out,`repository-${width}.png`)});
      await page.locator('[data-node="repo-select"]').click();
      assert.equal(await page.locator('#detail-title').textContent(),model.nodes['repo-select'].title);
      for(const tab of ['input','output','checks','recovery']) {
        await page.locator(`#tab-${tab}`).click();
        assert.equal(await page.locator(`#tab-${tab}`).getAttribute('aria-selected'),'true');
        assert.deepEqual(await page.locator('#detail-panel li').allTextContents(),model.nodes['repo-select'][tab]);
      }
      await page.locator('#tab-input').click();await page.locator('#tab-input').press('ArrowRight');
      assert.equal(await page.locator('#tab-output').getAttribute('aria-selected'),'true');
      await page.locator('#read-detail').click();assert(await page.locator('#reference-dialog').isVisible());
      assert((await page.locator('#reference-body').textContent()).includes('ordinal'));
      await sizeCheck();await page.keyboard.press('Escape');assert(!(await page.locator('#reference-dialog').isVisible()));
      await page.goBack();assert.equal(new URL(page.url()).hash,'#map=pre-repository');
      await page.locator('#up').click();assert.equal(new URL(page.url()).hash,'#map=preprocess');
      await page.locator('#overview-rail button').filter({hasText:model.nodes.load.title}).click();
      await settle();assert.equal(await page.locator('#connections > path').count(),0);
      await page.locator('[data-node="load-bootstrap"]').click();await page.locator('[data-node="bootstrap-copy"]').click();
      assert((await page.locator('#detail-summary').textContent()).includes('64MiB'));
      await page.reload();assert.equal(await page.locator('#detail-title').textContent(),model.nodes['bootstrap-copy'].title);
      await sizeCheck();
      results.push({...metrics,width,drilldown:true,tabs:true,keyboard:true,modal:true,history:true,deepLink:true});
    }
    // Every node and reference must be reachable, including leaves outside the example path.
    const visited=new Set();
    function visit(id){assert(!visited.has(id),`Cycle or duplicate parent: ${id}`);visited.add(id);for(const child of model.nodes[id].children)visit(child);}
    model.root.forEach(visit);assert.equal(visited.size,Object.keys(model.nodes).length);
    for(const [id,node] of Object.entries(model.nodes)) {
      assert.equal(await page.locator(`#${node.reference}`).count(),1,`Missing reference ${id}: ${node.reference}`);
      for(const field of ['input','process','output','checks','recovery'])assert(node[field]?.length,`${id}.${field} empty`);
    }
    // Glossary remains usable without a network, including dynamically rendered text.
    const tooltip=page.locator('#term-tooltip');
    for(const width of [375,1440]) {
      await page.setViewportSize({width,height:1000});await page.goto(url);
      const term=page.locator('#nodes .term-hint').first();
      await term.hover();await tooltip.waitFor({state:'visible'});
      assert.equal(await term.getAttribute('aria-describedby'),'term-tooltip');
      await tooltip.hover();await page.waitForTimeout(200);assert(await tooltip.isVisible());
      const box=await tooltip.boundingBox();assert(box.x>=0&&box.x+box.width<=width&&box.y>=0&&box.y+box.height<=1000);
      await page.screenshot({path:path.join(out,`tooltip-${width}.png`)});
      await page.keyboard.press('Escape');assert(!(await tooltip.isVisible()));
      const before=page.url();await term.click();assert(await tooltip.isVisible());assert.equal(page.url(),before);
      await page.locator('[data-node="preprocess"] .node-action').click();
      assert.equal(new URL(page.url()).hash,'#map=preprocess');
      await page.locator('[data-node="pre-repository"] .node-action').click();
      await page.locator('#read-detail').click();
      const modalTerm=page.locator('#reference-body .term-hint').first();
      await modalTerm.focus();await tooltip.waitFor({state:'visible'});
      assert.equal(await tooltip.evaluate(el=>el.parentElement.id),'reference-dialog');
      await page.keyboard.press('Escape');assert(!(await tooltip.isVisible()));assert(await page.locator('#reference-dialog').isVisible());
      await page.keyboard.press('Escape');assert(!(await page.locator('#reference-dialog').isVisible()));
      assert.equal(await page.locator('.term-hint .term-hint, pre .term-hint').count(),0);
    }
    // Exercise longest-match and ignored code paths through the same observer as inspector tabs.
    await page.locator('#detail-panel').evaluate(el=>{el.innerHTML='<p>bundle manifest SHA / manifest / SHA</p><pre>manifest SHA</pre><code>path/manifest.json</code>';});
    await settle();
    assert.deepEqual(await page.locator('#detail-panel .term-hint').allTextContents(),['bundle manifest SHA','manifest','SHA']);
    await page.locator('#detail-panel .term-hint').first().focus();await tooltip.waitFor({state:'visible'});
    assert.equal(await tooltip.locator('strong').textContent(),'bundle manifest SHA');
    await page.locator('#map-title').click();assert(!(await tooltip.isVisible()));
    await page.reload();
    const touchContext=await browser.newContext({offline:true,hasTouch:true,isMobile:true,viewport:{width:375,height:1000}});
    const touchPage=await touchContext.newPage();await touchPage.goto(url);
    const touchUrl=touchPage.url();await touchPage.locator('#nodes .term-hint').first().tap();
    assert(await touchPage.locator('#term-tooltip').isVisible());assert.equal(touchPage.url(),touchUrl);
    await touchPage.locator('[data-node="preprocess"] .node-action').tap();
    assert.equal(new URL(touchPage.url()).hash,'#map=preprocess');await touchContext.close();
    await page.locator('#view-toggle').click();assert(await page.locator('#reader').isVisible());
    assert.equal(await page.locator('article h2').count(),9);
    await page.locator('#view-toggle').click();assert(await page.locator('#explorer').isVisible());
    await page.evaluate(()=>dispatchEvent(new Event('beforeprint')));
    assert.equal(await page.locator('#reader details:not([open])').count(),0);
    await page.pdf({path:path.join(out,'guide-print.pdf'),format:'A4',printBackground:true,preferCSSPageSize:true});
    await page.evaluate(()=>dispatchEvent(new Event('afterprint')));
    const noJs=await browser.newContext({javaScriptEnabled:false,offline:true});const fallback=await noJs.newPage();
    await fallback.goto(url);assert(await fallback.locator('#reader').isVisible());assert.equal(await fallback.locator('article h2').count(),9);
    assert.deepEqual(errors,[]);assert.deepEqual(network,[]);
    const report={result:'PASS',nodes:visited.size,results,tooltips:true,errors,network,offline:true,noJsFallback:true,output:out};
    fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
