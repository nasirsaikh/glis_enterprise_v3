(function(){
  "use strict";

  const root=document.documentElement;
  const charts=new Map();

  const cssVar=(name,fallback)=>{
    const value=getComputedStyle(root).getPropertyValue(name).trim();
    return value||fallback;
  };
  const isDark=()=>root.getAttribute("data-theme")==="dark";
  const palette=()=>[
    cssVar("--color-primary","#167a52"),
    cssVar("--color-success","#16a34a"),
    cssVar("--color-warning","#d97706"),
    cssVar("--color-error","#dc2626"),
    cssVar("--color-info","#0284c7"),
    cssVar("--color-secondary","#7c3aed")
  ];
  const destroyChart=(id)=>{
    const chart=charts.get(id);
    if(chart){chart.destroy();charts.delete(id);}
  };
  const renderChart=(id,options)=>{
    const element=document.getElementById(id);
    if(!element||!window.ApexCharts)return;
    destroyChart(id);
    const chart=new ApexCharts(element,options);
    charts.set(id,chart);
    chart.render();
  };
  const commonChart=(type,height=250)=>({
    chart:{
      type,
      height,
      background:"transparent",
      foreColor:cssVar("--color-base-content","#475569"),
      fontFamily:"Inter, Cairo, sans-serif",
      toolbar:{show:false},
      animations:{enabled:true,speed:260}
    },
    theme:{mode:isDark()?"dark":"light"},
    grid:{borderColor:cssVar("--color-base-300","#e5e7eb"),strokeDashArray:3},
    dataLabels:{enabled:false},
    legend:{fontSize:"11px",labels:{colors:cssVar("--color-base-content","#475569")}},
    tooltip:{theme:isDark()?"dark":"light"}
  });

  const renderTPACharts=()=>{
    const qualitySource=document.getElementById("tpa-quality-data");
    const errorSource=document.getElementById("tpa-error-data");
    if(!qualitySource||!errorSource||!window.ApexCharts)return;

    const quality=JSON.parse(qualitySource.textContent||"[]");
    const errors=JSON.parse(errorSource.textContent||"[]");
    const qualityOptions=commonChart("donut",250);
    Object.assign(qualityOptions,{
      series:quality.map(item=>Number(item.value||0)),
      labels:quality.map(item=>item.label),
      colors:palette().slice(1,4),
      stroke:{width:2,colors:[cssVar("--color-base-100","#fff")]},
      plotOptions:{pie:{donut:{size:"68%",labels:{show:true,total:{show:true,label:"ROWS"}}}}},
      legend:{...qualityOptions.legend,position:"bottom"},
      noData:{text:"No member rows"}
    });
    renderChart("tpa-quality-chart",qualityOptions);

    const errorOptions=commonChart("bar",250);
    Object.assign(errorOptions,{
      series:[{name:"Rows",data:errors.map(item=>Number(item.value||0))}],
      colors:[cssVar("--color-error","#dc2626")],
      plotOptions:{bar:{horizontal:true,borderRadius:4,barHeight:"48%"}},
      xaxis:{categories:errors.map(item=>item.label),tickAmount:Math.max(1,Math.min(6,errors.length))},
      noData:{text:"No validation errors"},
      legend:{show:false}
    });
    renderChart("tpa-error-chart",errorOptions);
  };

  const setupPrincipal=()=>{
    const relationship=document.querySelector('[name="relationship"]');
    const principalField=document.getElementById("principal-reference-field");
    const principalSelect=document.querySelector('[name="principal_reference"]');
    if(!relationship||!principalField)return;
    const sync=()=>{
      const needed=Boolean(relationship.value&&relationship.value!=="PRINCIPAL");
      principalField.style.display=needed?"":"none";
      if(!needed&&principalSelect)principalSelect.value="";
    };
    if(relationship.dataset.tpaPrincipalReady!=="true"){
      relationship.dataset.tpaPrincipalReady="true";
      relationship.addEventListener("change",sync);
    }
    sync();
  };

  const setupDropzones=(scope=document)=>{
    scope.querySelectorAll("[data-tpa-dropzone]:not([data-tpa-ready])").forEach(zone=>{
      zone.dataset.tpaReady="true";
      const input=zone.querySelector('input[type="file"]');
      const count=zone.querySelector("[data-tpa-file-count]");
      if(!input)return;
      const update=()=>{
        const files=Array.from(input.files||[]);
        if(count)count.textContent=files.length?files.length+" file(s) selected":"No files selected";
      };
      zone.addEventListener("click",event=>{
        if(event.target.closest("button,a,input,label"))return;
        input.click();
      });
      ["dragenter","dragover"].forEach(name=>zone.addEventListener(name,event=>{
        event.preventDefault();zone.classList.add("is-dragging");
      }));
      ["dragleave","drop"].forEach(name=>zone.addEventListener(name,event=>{
        event.preventDefault();zone.classList.remove("is-dragging");
      }));
      zone.addEventListener("drop",event=>{
        if(event.dataTransfer?.files?.length){
          try{input.files=event.dataTransfer.files;}catch(_){}
          update();
        }
      });
      input.addEventListener("change",update);
    });
  };

  const init=(scope=document)=>{
    setupPrincipal();
    setupDropzones(scope);
    setTimeout(renderTPACharts,40);
  };

  document.addEventListener("DOMContentLoaded",()=>init());
  document.addEventListener("glis:theme",()=>setTimeout(renderTPACharts,60));
  document.body?.addEventListener("htmx:afterSwap",event=>init(event.detail.target));
})();
