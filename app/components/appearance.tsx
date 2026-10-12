"use client";
import {useEffect,useState} from "react";
const themes=[{id:"apricot",name:"Apricot",color:"#ea743d"},{id:"matcha",name:"Matcha",color:"#718255"},{id:"ink",name:"After hours",color:"#20201e"},{id:"plum",name:"Lilac",color:"#9580b6"}];
export function Appearance(){
  const [theme,setTheme]=useState("apricot");
  useEffect(()=>{let active=true;Promise.resolve().then(()=>{try{const saved=localStorage.getItem("admint:appearance");if(active&&themes.some(t=>t.id===saved))setTheme(saved!);}catch{}});return()=>{active=false;};},[]);
  function choose(id:string){setTheme(id);document.documentElement.setAttribute("data-art-theme",id);try{localStorage.setItem("admint:appearance",id);}catch{}}
  return <details className="appearance"><summary><span aria-hidden="true">◐</span> Appearance <span className="appearance-current">{themes.find(t=>t.id===theme)?.name}</span></summary><div className="appearance-options">{themes.map(t=><button key={t.id} aria-pressed={theme===t.id} onClick={()=>choose(t.id)}><span style={{background:t.color}}/>{t.name}<i>{theme===t.id?"✓":""}</i></button>)}</div></details>;
}
