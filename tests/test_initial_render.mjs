import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';

test('every bookmarked view renders before cohort data arrives; Lab exposes its task controls',async()=>{
  const previousLocation=globalThis.location,previousWindow=globalThis.window;
  const server=await createServer({server:{middlewareMode:true,hmr:false},logLevel:'silent'});
  try{
    globalThis.window={sessionStorage:{getItem:()=>null},matchMedia:()=>({matches:false})};
    const {App}=await server.ssrLoadModule('/src/main.jsx');
    for(const view of ['models','narratives','overview','reactions','reports','signals','changes','severity','network']){
      globalThis.location={hash:`#${view}`};
      const html=renderToStaticMarkup(React.createElement(App));
      assert.match(html,/<main /,view);
      assert.doesNotMatch(html,/This view needs a refresh/,view);
      if(view==='models'){
        assert.match(html,/Training sample size/);
        assert.match(html,/Train &amp; evaluate/);
        assert.match(html,/No records available/);
      }
      if(view==='narratives')assert.match(html,/id="narrative"/);
    }
  }finally{
    if(previousLocation===undefined)delete globalThis.location;else globalThis.location=previousLocation;
    if(previousWindow===undefined)delete globalThis.window;else globalThis.window=previousWindow;
    await server.close();
  }
});
