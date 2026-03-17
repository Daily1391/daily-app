import { useState, useEffect, useCallback } from "react";

// ─── Supabase ─────────────────────────────────────────────────────────────────
const SUPABASE_URL = "https://naevzmtrsjfyiqlpxfjt.supabase.co";
const SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5hZXZ6bXRyc2pmeWlxbHB4Zmp0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM2MTYyMTIsImV4cCI6MjA4OTE5MjIxMn0.k1HTUtCE5wtaLJhRHmZQQZlBP443HklqHzko707Sw_4";

const sb = async (path, options = {}) => {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    headers: {
      "apikey": SUPABASE_KEY,
      "Authorization": `Bearer ${options.token || SUPABASE_KEY}`,
      "Content-Type": "application/json",
      "Prefer": options.prefer || "return=representation",
      ...options.headers
    },
    ...options
  });
  if (!res.ok) { const e = await res.text(); throw new Error(e); }
  const text = await res.text();
  return text ? JSON.parse(text) : null;
};

const sbAuth = async (path, body) => {
  const res = await fetch(`${SUPABASE_URL}/auth/v1/${path}`, {
    method: "POST",
    headers: { "apikey": SUPABASE_KEY, "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  const data = await res.json();
  if (data.error) throw new Error(data.error_description || data.error);
  return data;
};

// ─── Constants ───────────────────────────────────────────────────────────────
const PRIORITIES = ["Low", "Medium", "High"];
const PRIORITY_ORDER = { High: 0, Medium: 1, Low: 2 };
const MONTH_NAMES = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const DAY_NAMES = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
const today = new Date();
const pad = n => String(n).padStart(2,"0");
const dateKey = d => `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
const todayKey = dateKey(today);
const parseDate = s => { const [y,m,d]=s.split("-").map(Number); return new Date(y,m-1,d); };
const getPriorityColor = p => ({Low:"#82B366",Medium:"#E8A838",High:"#E07070"}[p]||"#aaa");

function getWeekDays(ref) {
  const d=new Date(ref), mon=new Date(d);
  mon.setDate(d.getDate()-((d.getDay()+6)%7));
  return Array.from({length:7},(_,i)=>{const dd=new Date(mon);dd.setDate(mon.getDate()+i);return dd;});
}
function getMonthDays(year,month) {
  const first=new Date(year,month,1),last=new Date(year,month+1,0);
  const startPad=(first.getDay()+6)%7, days=[];
  for(let i=0;i<startPad;i++)days.push(null);
  for(let i=1;i<=last.getDate();i++)days.push(new Date(year,month,i));
  return days;
}
function recurringAppliesToDate(task,dateStr) {
  if(!task.repeat||task.repeat==="none")return false;
  if(task.disabled_from&&dateStr>=task.disabled_from)return false;
  if(dateStr<task.start_date)return false;
  if(task.repeat==="daily")return true;
  if(task.repeat==="weekly"){
    const diff=Math.round((parseDate(dateStr)-parseDate(task.start_date))/(86400000));
    return diff%7===0;
  }
  return false;
}

// ─── Onboarding ──────────────────────────────────────────────────────────────
const STEPS = [
  {icon:null,title:"daily",cursive:true,desc:"Your personal study companion. Stay on top of homework, tests, and deadlines — all in one clean place."},
  {icon:"🗓",title:"Three Views",desc:"Switch between Daily, Weekly, and Monthly to plan at whatever level suits you."},
  {icon:"✅",title:"Add & Check Off Tasks",desc:"Tap + on any day to add a task. Set a priority and notes. Check it off when done.",blueIcon:true},
  {icon:"🔁",title:"Repeating Tasks",desc:"Set tasks to repeat daily or weekly. Stop or manage them anytime from the Repeating panel."},
  {icon:"✦",title:"AI Planner",desc:"Type your schedule in plain English and the AI fills your calendar instantly.",purpleIcon:true},
];

function Onboarding({ onDone }) {
  const [step, setStep] = useState(0);
  const [authMode, setAuthMode] = useState("signup");
  const [form, setForm] = useState({name:"",email:"",password:""});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const total = STEPS.length + 1;
  const isAuth = step === STEPS.length;

  const handleAuth = async () => {
    if (!form.email || !form.password) { setError("Please fill in all fields."); return; }
    setLoading(true); setError("");
    try {
      if (authMode === "signup") {
        const data = await sbAuth("signup", { email: form.email, password: form.password });
        if (data.user) {
          await sb(`profiles`, { method: "POST", token: data.access_token, body: JSON.stringify({ id: data.user.id, name: form.name, email: form.email }) });
          localStorage.setItem("sb_token", data.access_token);
          localStorage.setItem("sb_user", JSON.stringify({ ...data.user, name: form.name }));
        }
      } else {
        const data = await sbAuth("token?grant_type=password", { email: form.email, password: form.password });
        localStorage.setItem("sb_token", data.access_token);
        localStorage.setItem("sb_user", JSON.stringify(data.user));
      }
      localStorage.setItem("onboarded", "true");
      onDone();
    } catch(e) { setError(e.message); }
    setLoading(false);
  };

  return (
    <div style={{position:"fixed",inset:0,background:isAuth?"#fff":"#0d0d0d",display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",padding:32,fontFamily:"'Inter',system-ui,sans-serif",transition:"background 0.4s",overflow:"hidden"}}>
      <style>{`@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600&display=swap');@keyframes fadeUp{from{opacity:0;transform:translateY(24px)}to{opacity:1;transform:translateY(0)}}`}</style>
      {!isAuth && <>
        <div style={{position:"absolute",inset:0,pointerEvents:"none"}}>
          <svg style={{width:"100%",height:"100%",opacity:0.07}} xmlns="http://www.w3.org/2000/svg">
            <defs><pattern id="grid" width="48" height="48" patternUnits="userSpaceOnUse"><circle cx="24" cy="24" r="1.5" fill="#fff"/></pattern></defs>
            <rect width="100%" height="100%" fill="url(#grid)"/>
          </svg>
          <div style={{position:"absolute",top:"-10%",left:"-5%",width:400,height:400,borderRadius:"50%",background:"radial-gradient(circle,rgba(108,142,191,0.15) 0%,transparent 70%)"}}/>
          <div style={{position:"absolute",bottom:"-10%",right:"-5%",width:500,height:500,borderRadius:"50%",background:"radial-gradient(circle,rgba(155,89,182,0.12) 0%,transparent 70%)"}}/>
        </div>
        <button onClick={() => { localStorage.setItem("onboarded","true"); onDone(); }} style={{position:"absolute",top:24,right:24,background:"rgba(255,255,255,0.1)",border:"1px solid rgba(255,255,255,0.15)",color:"rgba(255,255,255,0.6)",fontSize:13,fontWeight:600,padding:"7px 16px",borderRadius:20,cursor:"pointer",fontFamily:"inherit"}}>Skip</button>
      </>}

      {!isAuth && (
        <div key={step} style={{textAlign:"center",maxWidth:360,animation:"fadeUp 0.4s ease",position:"relative",zIndex:1}}>
          {STEPS[step].icon && (
            <div style={{fontSize:72,marginBottom:24,lineHeight:1}}>
              {STEPS[step].purpleIcon ? <span style={{background:"linear-gradient(135deg,#6C8EBF,#9B59B6)",WebkitBackgroundClip:"text",WebkitTextFillColor:"transparent"}}>{STEPS[step].icon}</span>
              : STEPS[step].blueIcon ? <span style={{color:"#6C8EBF"}}>{STEPS[step].icon}</span>
              : STEPS[step].icon}
            </div>
          )}
          {STEPS[step].cursive
            ? <div style={{marginBottom:12,lineHeight:1.2}}>
                <span style={{fontSize:22,color:"#fff"}}>Welcome to </span>
                <span style={{fontSize:60,fontWeight:600,color:"#fff",fontFamily:"'Cormorant Garamond',serif",marginLeft:8}}>daily</span>
              </div>
            : <div style={{fontSize:26,fontWeight:700,color:"#fff",marginBottom:12}}>{STEPS[step].title}</div>
          }
          <div style={{fontSize:15,color:"#fff",lineHeight:1.75,marginBottom:48}}>{STEPS[step].desc}</div>
        </div>
      )}

      {isAuth && (
        <div key="auth" style={{width:"100%",maxWidth:380,animation:"fadeUp 0.4s ease"}}>
          <div style={{textAlign:"center",marginBottom:28}}>
            <div style={{fontSize:42,fontWeight:600,color:"#111",fontFamily:"'Cormorant Garamond',serif",marginBottom:8}}>daily</div>
            <div style={{fontSize:20,fontWeight:700,color:"#111",marginBottom:4}}>{authMode==="signup"?"Create your account":"Welcome back"}</div>
            <div style={{fontSize:13,color:"#aaa"}}>{authMode==="signup"?"Save your tasks across every device.":"Log back in to your planner."}</div>
          </div>
          <div style={{display:"flex",background:"#f0f0f0",borderRadius:12,padding:4,marginBottom:18,gap:2}}>
            {["signup","login"].map(m=>(
              <button key={m} onClick={()=>{setAuthMode(m);setError("");}} style={{flex:1,padding:"9px 0",borderRadius:9,border:"none",cursor:"pointer",background:authMode===m?"#fff":"transparent",color:authMode===m?"#111":"#aaa",fontWeight:authMode===m?700:500,fontSize:13,fontFamily:"inherit",transition:"all 0.2s",boxShadow:authMode===m?"0 1px 4px rgba(0,0,0,0.08)":"none"}}>
                {m==="signup"?"Sign Up":"Log In"}
              </button>
            ))}
          </div>
          {authMode==="signup"&&<input placeholder="Your name" value={form.name} onChange={e=>setForm(f=>({...f,name:e.target.value}))} style={{width:"100%",padding:"13px 16px",borderRadius:12,border:"1.5px solid #e8e8e8",fontSize:14,marginBottom:10,outline:"none",boxSizing:"border-box",fontFamily:"inherit",color:"#111"}}/>}
          <input placeholder="Email address" value={form.email} onChange={e=>setForm(f=>({...f,email:e.target.value}))} style={{width:"100%",padding:"13px 16px",borderRadius:12,border:"1.5px solid #e8e8e8",fontSize:14,marginBottom:10,outline:"none",boxSizing:"border-box",fontFamily:"inherit",color:"#111"}}/>
          <input placeholder="Password" type="password" value={form.password} onChange={e=>setForm(f=>({...f,password:e.target.value}))} onKeyDown={e=>e.key==="Enter"&&handleAuth()} style={{width:"100%",padding:"13px 16px",borderRadius:12,border:"1.5px solid #e8e8e8",fontSize:14,marginBottom:10,outline:"none",boxSizing:"border-box",fontFamily:"inherit",color:"#111"}}/>
          {error && <div style={{fontSize:13,color:"#E07070",marginBottom:10,fontWeight:500}}>{error}</div>}
          <button onClick={handleAuth} disabled={loading} style={{width:"100%",padding:"14px 0",borderRadius:12,border:"none",background:"#111",color:"#fff",fontSize:15,fontWeight:700,cursor:loading?"not-allowed":"pointer",fontFamily:"inherit",marginBottom:10,opacity:loading?0.7:1}}>
            {loading?"Please wait...":(authMode==="signup"?"Get Started →":"Log In →")}
          </button>
          <button onClick={()=>{localStorage.setItem("onboarded","true");onDone();}} style={{width:"100%",padding:"13px 0",borderRadius:12,border:"1.5px solid #e8e8e8",background:"#fff",color:"#aaa",fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>Continue without account</button>
        </div>
      )}

      <div style={{display:"flex",gap:8,marginTop:isAuth?24:0,marginBottom:isAuth?0:28,position:"relative",zIndex:1}}>
        {Array.from({length:total}).map((_,i)=>(
          <div key={i} onClick={()=>setStep(i)} style={{width:i===step?24:8,height:8,borderRadius:4,background:isAuth?(i===step?"#111":"#ddd"):(i===step?"#fff":"rgba(255,255,255,0.25)"),transition:"all 0.3s",cursor:"pointer"}}/>
        ))}
      </div>

      {!isAuth && (
        <button onClick={()=>setStep(s=>s+1)} style={{padding:"14px 48px",borderRadius:50,border:"1px solid rgba(255,255,255,0.2)",background:"rgba(255,255,255,0.1)",color:"#fff",fontSize:15,fontWeight:700,cursor:"pointer",fontFamily:"inherit",position:"relative",zIndex:1}}>
          Next →
        </button>
      )}
    </div>
  );
}

const AddBtn = ({onClick}) => (
  <button onClick={onClick} style={{width:26,height:26,borderRadius:"50%",border:"none",background:"#6C8EBF",color:"#fff",fontSize:20,cursor:"pointer",display:"grid",placeItems:"center",lineHeight:1,flexShrink:0,fontFamily:"inherit",paddingBottom:1}}>+</button>
);

export default function App() {
  const [onboarded, setOnboarded] = useState(() => JSON.parse(localStorage.getItem("onboarded")||"false"));
  if (!onboarded) return <Onboarding onDone={()=>setOnboarded(true)} />;
  return <Planner />;
}

function Planner() {
  const token = localStorage.getItem("sb_token");
  const sbUser = JSON.parse(localStorage.getItem("sb_user")||"null");

  const [dark,setDark]=useState(()=>JSON.parse(localStorage.getItem("dark")||"false"));
  const [view,setView]=useState("daily");
  const [oneOffTasks,setOneOffTasks]=useState({});
  const [recurringTasks,setRecurringTasks]=useState([]);
  const [completedRecurring,setCompletedRecurring]=useState({});
  const [ref,setRef]=useState(new Date(today));
  const [modal,setModal]=useState(null);
  const [form,setForm]=useState({title:"",priority:"Medium",repeat:"none",notes:""});
  const [removingIds,setRemovingIds]=useState({});
  const [checkAnim,setCheckAnim]=useState(false);
  const [aiOpen,setAiOpen]=useState(false);
  const [manageOpen,setManageOpen]=useState(false);
  const [settingsOpen,setSettingsOpen]=useState(false);
  const [settingsForm,setSettingsForm]=useState({name:sbUser?.name||"",email:sbUser?.email||""});
  const [settingsSaved,setSettingsSaved]=useState(false);
  const [aiInput,setAiInput]=useState("");
  const [aiLoading,setAiLoading]=useState(false);
  const [aiMsg,setAiMsg]=useState("");
  const [loading,setLoading]=useState(true);

  useEffect(()=>{localStorage.setItem("dark",JSON.stringify(dark));},[dark]);

  // Load all data from Supabase
  const loadData = useCallback(async () => {
    if (!token) { setLoading(false); return; }
    try {
      const [tasks, recurring, completed, profile] = await Promise.all([
        sb(`tasks?user_id=eq.${sbUser.id}&order=created_at.asc`, { token }),
        sb(`recurring_tasks?user_id=eq.${sbUser.id}`, { token }),
        sb(`completed_recurring?user_id=eq.${sbUser.id}`, { token }),
        sb(`profiles?id=eq.${sbUser.id}`, { token })
      ]);

      // Group tasks by date
      const oot = {};
      (tasks||[]).forEach(t => { if(!oot[t.date])oot[t.date]=[]; oot[t.date].push({id:t.id,title:t.title,priority:t.priority,notes:t.notes,done:t.done}); });
      setOneOffTasks(oot);
      setRecurringTasks((recurring||[]).map(t=>({...t,startDate:t.start_date,disabledFrom:t.disabled_from})));

      // Group completed recurring by date
      const cr = {};
      (completed||[]).forEach(c => { if(!cr[c.date])cr[c.date]=[]; cr[c.date].push(c.task_id); });
      setCompletedRecurring(cr);

      if (profile?.[0]) setSettingsForm({name:profile[0].name||"",email:profile[0].email||""});
    } catch(e) { console.error(e); }
    setLoading(false);
  }, [token]);

  useEffect(()=>{ loadData(); },[loadData]);

  const getTasksForDate=(dateStr)=>{
    const oo=oneOffTasks[dateStr]||[];
    const completed=completedRecurring[dateStr]||[];
    const rec=recurringTasks.filter(t=>recurringAppliesToDate(t,dateStr)&&!completed.includes(t.id)).map(t=>({...t,isRecurring:true}));
    return [...oo,...rec].sort((a,b)=>PRIORITY_ORDER[a.priority]-PRIORITY_ORDER[b.priority]);
  };

  const openModal=date=>{setModal({date});setForm({title:"",priority:"Medium",repeat:"none",notes:""});};

  const addTask=async(date)=>{
    if(!form.title.trim())return;
    const k=dateKey(date);
    const id=Date.now().toString();
    if(form.repeat==="none"){
      const task={id,title:form.title.trim(),priority:form.priority,notes:form.notes,done:false};
      setOneOffTasks(t=>({...t,[k]:[...(t[k]||[]),task]}));
      if(token) await sb(`tasks`,{method:"POST",token,prefer:"return=minimal",body:JSON.stringify({id,user_id:sbUser.id,date:k,title:task.title,priority:task.priority,notes:task.notes,done:false})});
      if(form.priority==="High") scheduleNotification(task,date);
    } else {
      const task={id,title:form.title.trim(),priority:form.priority,notes:form.notes,repeat:form.repeat,startDate:k,start_date:k};
      setRecurringTasks(t=>[...t,task]);
      if(token) await sb(`recurring_tasks`,{method:"POST",token,prefer:"return=minimal",body:JSON.stringify({id,user_id:sbUser.id,title:task.title,priority:task.priority,notes:task.notes,repeat:task.repeat,start_date:k})});
      if(form.priority==="High") scheduleNotification(task,date);
    }
    setForm({title:"",priority:"Medium",repeat:"none",notes:""});
    setModal(null);
  };

  const toggleTask=async(dateStr,taskId,isRecurring)=>{
    setCheckAnim(true);
    setTimeout(()=>setCheckAnim(false),950);
    setOneOffTasks(t=>({...t,[dateStr]:(t[dateStr]||[]).map(task=>task.id===taskId?{...task,done:true}:task)}));
    setTimeout(()=>setRemovingIds(r=>({...r,[taskId]:true})),600);
    setTimeout(async()=>{
      if(isRecurring){
        setCompletedRecurring(c=>({...c,[dateStr]:[...(c[dateStr]||[]),taskId]}));
        if(token) await sb(`completed_recurring`,{method:"POST",token,prefer:"return=minimal",body:JSON.stringify({user_id:sbUser.id,date:dateStr,task_id:taskId})});
      } else {
        setOneOffTasks(t=>({...t,[dateStr]:(t[dateStr]||[]).filter(task=>task.id!==taskId)}));
        if(token) await sb(`tasks?id=eq.${taskId}`,{method:"DELETE",token,prefer:"return=minimal"});
      }
      setRemovingIds(r=>{const n={...r};delete n[taskId];return n;});
    },950);
  };

  const deleteOneOff=async(dateStr,id)=>{
    setOneOffTasks(t=>({...t,[dateStr]:(t[dateStr]||[]).filter(task=>task.id!==id)}));
    if(token) await sb(`tasks?id=eq.${id}`,{method:"DELETE",token,prefer:"return=minimal"});
  };

  const disableRecurring=async(id,fromDate)=>{
    setRecurringTasks(t=>t.map(task=>task.id===id?{...task,disabledFrom:fromDate,disabled_from:fromDate}:task));
    if(token) await sb(`recurring_tasks?id=eq.${id}`,{method:"PATCH",token,prefer:"return=minimal",body:JSON.stringify({disabled_from:fromDate})});
  };

  const deleteRecurring=async(id)=>{
    setRecurringTasks(t=>t.filter(task=>task.id!==id));
    if(token) await sb(`recurring_tasks?id=eq.${id}`,{method:"DELETE",token,prefer:"return=minimal"});
  };

  const saveSettings=async()=>{
    setSettingsSaved(true);
    localStorage.setItem("account_v1",JSON.stringify(settingsForm));
    if(token) await sb(`profiles?id=eq.${sbUser.id}`,{method:"PATCH",token,prefer:"return=minimal",body:JSON.stringify({name:settingsForm.name,email:settingsForm.email})});
    setTimeout(()=>{setSettingsOpen(false);setSettingsSaved(false);},1000);
  };

  const requestNotifPermission=async()=>{ if("Notification"in window&&Notification.permission==="default") await Notification.requestPermission(); };
  const scheduleNotification=(task,date)=>{
    if(!("Notification"in window)||Notification.permission!=="granted")return;
    if(dateKey(new Date(date))===todayKey) setTimeout(()=>new Notification("⚠️ High Priority Reminder",{body:`Don't forget: "${task.title}" is due today!`}),3000);
  };
  useEffect(()=>{requestNotifPermission();},[]);

  const getProgress=dateStr=>{
    const active=getTasksForDate(dateStr);
    const compToday=(completedRecurring[dateStr]||[]).filter(id=>{const r=recurringTasks.find(rt=>rt.id===id);return r&&recurringAppliesToDate(r,dateStr);});
    const total=active.length+compToday.length;
    return total?Math.round(compToday.length/total*100):0;
  };

  const nav=dir=>{
    const d=new Date(ref);
    if(view==="daily")d.setDate(d.getDate()+dir);
    else if(view==="weekly")d.setDate(d.getDate()+dir*7);
    else d.setMonth(d.getMonth()+dir);
    setRef(d);
  };

  const weekDays=getWeekDays(ref);
  const getDashStats=()=>{
    let dates=[];
    if(view==="daily")dates=[dateKey(ref)];
    else if(view==="weekly")dates=weekDays.map(d=>dateKey(d));
    else dates=getMonthDays(ref.getFullYear(),ref.getMonth()).filter(Boolean).map(d=>dateKey(d));
    const allActive=dates.flatMap(ds=>getTasksForDate(ds));
    const allComp=dates.flatMap(ds=>(completedRecurring[ds]||[]).filter(id=>{const r=recurringTasks.find(rt=>rt.id===id);return r&&recurringAppliesToDate(r,ds);}));
    const total=allActive.length+allComp.length,done=allComp.length;
    return{total,done,pct:total?Math.round(done/total*100):0};
  };
  const {total:dashTotal,done:dashDone,pct:dashPct}=getDashStats();
  const dashLabel=view==="weekly"?`This Week — ${MONTH_NAMES[weekDays[0].getMonth()]} ${weekDays[0].getDate()}–${weekDays[6].getDate()}`:view==="monthly"?`${MONTH_NAMES[ref.getMonth()]} ${ref.getFullYear()}`:`Today — ${MONTH_NAMES[today.getMonth()]} ${today.getDate()}`;
  const motivational=dashTotal===0?`Add your first task for ${view==="daily"?"today":view==="weekly"?"this week":"this month"}!`:dashPct===100?"All done — great work! 🎉":dashPct>=50?"Halfway there, keep going!":"You've got this, let's get started!";

  const handleAiSubmit=async()=>{
    if(!aiInput.trim())return;
    setAiLoading(true);setAiMsg("");
    try{
      const res=await fetch("https://api.anthropic.com/v1/messages",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({model:"claude-sonnet-4-20250514",max_tokens:1000,system:`Extract tasks from natural language. Return ONLY a JSON array, no markdown. Each item: {"date":"YYYY-MM-DD","title":"task","priority":"High"|"Medium"|"Low"}. Current year:${today.getFullYear()}, month:${today.getMonth()+1}.`,messages:[{role:"user",content:aiInput}]})});
      const data=await res.json();
      const raw=data.content.find(b=>b.type==="text")?.text||"[]";
      const parsed=JSON.parse(raw.replace(/```json|```/g,"").trim());
      if(!Array.isArray(parsed)||!parsed.length){setAiMsg("Couldn't find any tasks. Try being more specific!");setAiLoading(false);return;}
      for(const {date,title,priority} of parsed){
        if(!date||!title)continue;
        const id=Date.now().toString()+Math.random();
        const task={id,title,priority:priority||"Medium",notes:"",done:false};
        setOneOffTasks(t=>({...t,[date]:[...(t[date]||[]),task]}));
        if(token) await sb(`tasks`,{method:"POST",token,prefer:"return=minimal",body:JSON.stringify({id,user_id:sbUser.id,date,title,priority:priority||"Medium",notes:"",done:false})});
      }
      setAiMsg(`✓ Added ${parsed.length} task${parsed.length>1?"s":""} to your planner!`);
      setAiInput("");
    }catch{setAiMsg("Something went wrong. Please try again.");}
    setAiLoading(false);
  };

  const bg=dark?"#0f0f13":"#f5f5f7",card=dark?"#1a1a24":"#fff",cardBorder=dark?"#2a2a3a":"#f0f0f0";
  const text=dark?"#e8e8f0":"#2d2d2d",sub=dark?"#6b6b80":"#aaa",dayBg=dark?"#13131c":"#fafafa";
  const todayBg=dark?"#1a2035":"#EEF3FF",todayBorder=dark?"#4a6aaf":"#6C8EBF";
  const inputBg=dark?"#1a1a24":"#fff",inputBorder=dark?"#2a2a3a":"#eee";
  const modalInput={width:"100%",padding:"11px 14px",borderRadius:10,border:`1.5px solid ${inputBorder}`,fontSize:14,outline:"none",boxSizing:"border-box",fontFamily:"inherit",background:inputBg,color:text};

  const NavBtn=({children,onClick})=>(<button onClick={onClick} style={{background:"none",border:"none",fontSize:26,color:sub,cursor:"pointer",padding:"0 8px",lineHeight:1}}>{children}</button>);

  const ProgressBar=({dateStr})=>{
    const p=getProgress(dateStr);
    const active=getTasksForDate(dateStr);
    const comp=(completedRecurring[dateStr]||[]).filter(id=>{const r=recurringTasks.find(rt=>rt.id===id);return r&&recurringAppliesToDate(r,dateStr);});
    if(!active.length&&!comp.length)return null;
    return(<div style={{marginBottom:8}}><div style={{height:4,background:dark?"#2a2a3a":"#e8e8e8",borderRadius:4,overflow:"hidden"}}><div style={{height:"100%",width:`${p}%`,background:p===100?"#82B366":"#6C8EBF",borderRadius:4,transition:"width 0.4s"}}/></div><div style={{fontSize:10,color:sub,marginTop:2,textAlign:"right"}}>{p}% done</div></div>);
  };

  const TaskItem=({task,dateStr,compact})=>(
    <div style={{display:"flex",alignItems:"center",gap:10,padding:compact?"8px 10px":"10px 12px",background:card,borderRadius:10,marginBottom:6,boxShadow:dark?"none":"0 1px 4px rgba(0,0,0,0.06)",border:`1px solid ${cardBorder}`,opacity:removingIds[task.id]?0:1,transform:removingIds[task.id]?"translateX(12px)":"translateX(0)",transition:"opacity 0.35s ease,transform 0.35s ease"}}>
      <div onClick={()=>toggleTask(dateStr,task.id,task.isRecurring)} style={{width:compact?16:20,height:compact?16:20,borderRadius:"50%",flexShrink:0,cursor:"pointer",border:`2px solid ${task.done?"#82B366":dark?"#3a3a5a":"#ccc"}`,background:task.done?"#82B366":"transparent",display:"grid",placeItems:"center",transition:"all 0.2s"}}>
        {task.done&&<svg width="8" height="8" viewBox="0 0 10 10"><polyline points="1.5,5 4,7.5 8.5,2.5" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>}
      </div>
      <div style={{flex:1,minWidth:0}}>
        <div style={{display:"flex",alignItems:"center",gap:5}}>
          <div style={{fontSize:compact?12.5:13.5,fontWeight:500,color:task.done?sub:text,textDecoration:task.done?"line-through":"none",whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis"}}>{task.title}</div>
          {task.isRecurring&&<span style={{fontSize:9,background:dark?"#2a2a3a":"#e8edf5",color:"#6C8EBF",borderRadius:4,padding:"1px 5px",fontWeight:700,flexShrink:0}}>{task.repeat}</span>}
        </div>
        <div style={{fontSize:10.5,color:getPriorityColor(task.priority),fontWeight:600,marginTop:2}}>{task.priority}{!compact&&" Priority"}</div>
        {task.notes&&!compact&&<div style={{fontSize:11,color:sub,marginTop:2,whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis"}}>{task.notes}</div>}
      </div>
      {task.isRecurring
        ?<div onClick={()=>disableRecurring(task.id,dateKey(today))} title="Stop repeating" style={{cursor:"pointer",color:dark?"#3a3a5a":"#ccc",fontSize:14,padding:4}}>⊘</div>
        :<div onClick={()=>deleteOneOff(dateStr,task.id)} style={{cursor:"pointer",color:dark?"#3a3a5a":"#ccc",fontSize:18,lineHeight:1,padding:4}}>×</div>}
    </div>
  );

  const DayBlock=({date,compact})=>{
    const dateStr=dateKey(date),ts=getTasksForDate(dateStr),isToday=dateStr===todayKey;
    return(
      <div style={{padding:"12px 14px",background:isToday?todayBg:dayBg,borderRadius:14,border:`1.5px solid ${isToday?todayBorder:cardBorder}`}}>
        <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:8}}>
          <div><div style={{fontSize:11,color:sub,textTransform:"uppercase",letterSpacing:1}}>{DAY_NAMES[(date.getDay()+6)%7]}</div><div style={{fontSize:compact?18:22,fontWeight:700,color:isToday?"#6C8EBF":text}}>{date.getDate()}</div></div>
          <AddBtn onClick={()=>openModal(date)}/>
        </div>
        <ProgressBar dateStr={dateStr}/>
        <div style={{overflowY:"auto",maxHeight:compact?200:340}}>
          {ts.map(t=><TaskItem key={t.id} task={t} dateStr={dateStr} compact={compact}/>)}
          {!ts.length&&<div style={{fontSize:12,color:sub,textAlign:"center",marginTop:12}}>No tasks</div>}
        </div>
      </div>
    );
  };

  const Daily=()=>(<div><div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:20}}><NavBtn onClick={()=>nav(-1)}>‹</NavBtn><div style={{textAlign:"center"}}><div style={{fontSize:22,fontWeight:700,color:text}}>{MONTH_NAMES[ref.getMonth()]} {ref.getDate()}</div><div style={{fontSize:13,color:sub}}>{ref.getFullYear()}</div></div><NavBtn onClick={()=>nav(1)}>›</NavBtn></div><DayBlock date={ref} compact={false}/></div>);

  const Weekly=()=>{
    const days=getWeekDays(ref);
    return(<div><div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:20}}><NavBtn onClick={()=>nav(-1)}>‹</NavBtn><div style={{fontSize:17,fontWeight:700,color:text}}>{MONTH_NAMES[days[0].getMonth()]} {days[0].getDate()} – {days[6].getDate()}, {days[6].getFullYear()}</div><NavBtn onClick={()=>nav(1)}>›</NavBtn></div>
      <div style={{display:"flex",flexDirection:"column",gap:8}}>{days.map((d,i)=>{const dateStr=dateKey(d),ts=getTasksForDate(dateStr),isToday=dateStr===todayKey,p=getProgress(dateStr);return(<div key={i} style={{borderRadius:14,padding:"12px 14px",background:isToday?todayBg:dayBg,border:`1.5px solid ${isToday?todayBorder:cardBorder}`}}><div style={{display:"flex",alignItems:"center",gap:14,marginBottom:ts.length?8:0}}><div style={{width:48,flexShrink:0}}><div style={{fontSize:10,color:sub,textTransform:"uppercase",letterSpacing:0.8,fontWeight:600}}>{DAY_NAMES[(d.getDay()+6)%7]}</div><div style={{fontSize:20,fontWeight:700,color:isToday?"#6C8EBF":text}}>{d.getDate()}</div></div><div style={{flex:1}}>{ts.length>0?<><div style={{height:4,background:dark?"#2a2a3a":"#e8e8e8",borderRadius:4,overflow:"hidden"}}><div style={{height:"100%",width:`${p}%`,background:p===100?"#82B366":"#6C8EBF",borderRadius:4,transition:"width 0.4s"}}/></div><div style={{fontSize:10,color:sub,marginTop:2}}>{p}% done</div></>:<div style={{fontSize:12,color:sub}}>No tasks</div>}</div><AddBtn onClick={()=>openModal(d)}/></div>{ts.length>0&&<div style={{display:"flex",flexDirection:"column"}}>{ts.map(t=><TaskItem key={t.id} task={t} dateStr={dateStr} compact={true}/>)}</div>}</div>);})}</div>
    </div>);
  };

  const Monthly=()=>{
    const days=getMonthDays(ref.getFullYear(),ref.getMonth());
    return(<div><div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:20}}><NavBtn onClick={()=>nav(-1)}>‹</NavBtn><div style={{fontSize:20,fontWeight:700,color:text}}>{MONTH_NAMES[ref.getMonth()]} {ref.getFullYear()}</div><NavBtn onClick={()=>nav(1)}>›</NavBtn></div>
      <div style={{display:"grid",gridTemplateColumns:"repeat(7,1fr)",gap:4,marginBottom:4}}>{DAY_NAMES.map(d=><div key={d} style={{textAlign:"center",fontSize:11,color:sub,fontWeight:600,padding:"4px 0"}}>{d}</div>)}</div>
      <div style={{display:"grid",gridTemplateColumns:"repeat(7,1fr)",gap:4}}>{days.map((d,i)=>{if(!d)return<div key={i}/>;const dateStr=dateKey(d),ts=getTasksForDate(dateStr),isToday=dateStr===todayKey,p=getProgress(dateStr);return(<div key={i} onClick={()=>{setView("daily");setRef(new Date(d));}} style={{borderRadius:10,padding:"8px 6px",minHeight:72,cursor:"pointer",background:isToday?todayBg:dayBg,border:`1.5px solid ${isToday?todayBorder:cardBorder}`}}><div style={{fontSize:13,fontWeight:700,color:isToday?"#6C8EBF":text,marginBottom:4}}>{d.getDate()}</div>{ts.length>0&&<><div style={{height:3,background:dark?"#2a2a3a":"#e8e8e8",borderRadius:4,overflow:"hidden",marginBottom:4}}><div style={{height:"100%",width:`${p}%`,background:p===100?"#82B366":"#6C8EBF",borderRadius:4}}/></div><div style={{fontSize:10,color:sub}}>{ts.length} task{ts.length>1?"s":""}</div></>}</div>);})}</div>
    </div>);
  };

  if(loading) return <div style={{minHeight:"100vh",background:bg,display:"flex",alignItems:"center",justifyContent:"center",fontFamily:"'Cormorant Garamond',serif",fontSize:42,color:text}}>daily</div>;

  return(
    <div style={{minHeight:"100vh",background:bg,fontFamily:"'Inter',system-ui,sans-serif",padding:"24px 16px",transition:"background 0.3s"}}>
      <style>{`@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600&display=swap');@keyframes bgFade{0%{opacity:0}20%{opacity:1}75%{opacity:1}100%{opacity:0}}@keyframes checkPop{0%{transform:scale(0.5);opacity:0}50%{transform:scale(1.08);opacity:1}100%{transform:scale(1);opacity:1}}@keyframes wholeOut{0%{opacity:1}65%{opacity:1}100%{opacity:0}}@keyframes slideUp{from{transform:translateY(20px);opacity:0}to{transform:translateY(0);opacity:1}}`}</style>

      {checkAnim&&(<div style={{position:"fixed",inset:0,zIndex:999,display:"flex",alignItems:"center",justifyContent:"center",pointerEvents:"none",animation:"wholeOut 1.1s ease forwards"}}><div style={{position:"absolute",inset:0,background:dark?"rgba(15,15,19,0.7)":"rgba(245,245,247,0.7)",backdropFilter:"blur(6px)",animation:"bgFade 1.1s ease forwards"}}/><div style={{position:"relative",animation:"checkPop 0.35s cubic-bezier(0.34,1.56,0.64,1) forwards"}}><svg width="90" height="90" viewBox="0 0 90 90"><circle cx="45" cy="45" r="38" fill="rgba(108,142,191,0.12)"/><circle cx="45" cy="45" r="38" fill="none" stroke="#6C8EBF" strokeWidth="2.5"/><polyline points="28,46 40,58 63,33" fill="none" stroke="#6C8EBF" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round"/></svg></div></div>)}

      <div style={{maxWidth:960,margin:"0 auto"}}>
        <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:12}}>
          <div><div style={{fontSize:52,fontWeight:600,color:text,fontFamily:"'Cormorant Garamond',serif",lineHeight:1}}>daily</div></div>
          <button onClick={()=>setSettingsOpen(true)} style={{width:36,height:36,borderRadius:"50%",border:`1.5px solid ${cardBorder}`,background:card,color:text,cursor:"pointer",display:"grid",placeItems:"center"}}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
          </button>
        </div>

        <div style={{marginBottom:20,display:"flex",alignItems:"center",justifyContent:"space-between",flexWrap:"wrap",gap:10}}>
          <div style={{fontSize:13,color:sub}}>{(()=>{const h=new Date().getHours();const g=h<12?"Good morning":h<17?"Good afternoon":"Good evening";const n=settingsForm.name?`, ${settingsForm.name}`:"";return`${g}${n}!`;})()}</div>
          <div style={{display:"flex",alignItems:"center",gap:10,flexWrap:"wrap"}}>
            <button onClick={()=>setAiOpen(true)} style={{padding:"8px 16px",borderRadius:10,border:"none",background:"linear-gradient(135deg,#6C8EBF,#9B59B6)",color:"#fff",fontWeight:700,fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>✦ AI Planner</button>
            <button onClick={()=>setManageOpen(true)} style={{padding:"8px 14px",borderRadius:10,border:`1.5px solid ${cardBorder}`,background:card,color:text,fontSize:13,cursor:"pointer",fontFamily:"inherit"}}>↻ Repeating</button>
            <div style={{display:"flex",background:dark?"#1a1a24":"#ececec",borderRadius:12,padding:4,gap:2}}>
              {["daily","weekly","monthly"].map(v=>(<button key={v} onClick={()=>setView(v)} style={{padding:"7px 14px",borderRadius:9,border:"none",cursor:"pointer",background:view===v?card:"transparent",color:view===v?text:sub,fontWeight:view===v?700:500,fontSize:13,boxShadow:view===v?"0 1px 4px rgba(0,0,0,0.08)":"none",transition:"all 0.2s",textTransform:"capitalize",fontFamily:"inherit"}}>{v}</button>))}
            </div>
          </div>
        </div>

        <div style={{background:card,borderRadius:16,padding:"16px 20px",marginBottom:16,border:`1.5px solid ${cardBorder}`,display:"flex",alignItems:"center",gap:20,flexWrap:"wrap"}}>
          <div style={{flex:1,minWidth:160}}><div style={{fontSize:11,color:sub,fontWeight:600,textTransform:"uppercase",letterSpacing:1,marginBottom:4}}>{dashLabel}</div><div style={{fontSize:15,fontWeight:600,color:text}}>{motivational}</div></div>
          <div style={{display:"flex",gap:20,alignItems:"center"}}>
            <div style={{textAlign:"center"}}><div style={{fontSize:26,fontWeight:800,color:"#6C8EBF"}}>{dashTotal}</div><div style={{fontSize:11,color:sub}}>tasks</div></div>
            <div style={{textAlign:"center"}}><div style={{fontSize:26,fontWeight:800,color:"#82B366"}}>{dashDone}</div><div style={{fontSize:11,color:sub}}>done</div></div>
            <div style={{width:56,height:56,position:"relative"}}>
              <svg width="56" height="56" viewBox="0 0 56 56"><circle cx="28" cy="28" r="22" fill="none" stroke={dark?"#2a2a3a":"#e8e8e8"} strokeWidth="5"/><circle cx="28" cy="28" r="22" fill="none" stroke={dashPct===100?"#82B366":"#6C8EBF"} strokeWidth="5" strokeDasharray={138} strokeDashoffset={138-138*dashPct/100} strokeLinecap="round" style={{transform:"rotate(-90deg)",transformOrigin:"28px 28px",transition:"stroke-dashoffset 0.5s ease"}}/></svg>
              <div style={{position:"absolute",inset:0,display:"flex",alignItems:"center",justifyContent:"center",fontSize:11,fontWeight:700,color:text}}>{dashPct}%</div>
            </div>
          </div>
        </div>

        <div style={{background:card,borderRadius:20,padding:"24px 20px",boxShadow:dark?"none":"0 2px 16px rgba(0,0,0,0.06)",border:`1.5px solid ${cardBorder}`}}>
          {view==="daily"&&<Daily/>}{view==="weekly"&&<Weekly/>}{view==="monthly"&&<Monthly/>}
        </div>
      </div>

      {modal&&(<div style={{position:"fixed",inset:0,background:"rgba(0,0,0,0.35)",display:"flex",alignItems:"center",justifyContent:"center",zIndex:100,padding:16}}><div style={{background:card,borderRadius:20,padding:28,width:"100%",maxWidth:400,boxShadow:"0 8px 40px rgba(0,0,0,0.2)",animation:"slideUp 0.25s ease"}}><div style={{fontSize:17,fontWeight:700,marginBottom:18,color:text}}>Add Task — {MONTH_NAMES[modal.date.getMonth()]} {modal.date.getDate()}</div><input autoFocus placeholder="Task title..." value={form.title} onChange={e=>setForm(f=>({...f,title:e.target.value}))} onKeyDown={e=>e.key==="Enter"&&addTask(modal.date)} style={{...modalInput,marginBottom:10}}/><textarea placeholder="Notes (optional)..." value={form.notes} onChange={e=>setForm(f=>({...f,notes:e.target.value}))} rows={2} style={{...modalInput,marginBottom:12,resize:"none"}}/><div style={{marginBottom:12}}><div style={{fontSize:11,color:sub,marginBottom:6,fontWeight:600}}>PRIORITY</div><div style={{display:"flex",gap:8}}>{PRIORITIES.map(p=><button key={p} onClick={()=>setForm(f=>({...f,priority:p}))} style={{flex:1,padding:"8px 0",borderRadius:10,border:`1.5px solid ${form.priority===p?getPriorityColor(p):inputBorder}`,background:form.priority===p?getPriorityColor(p):inputBg,color:form.priority===p?"#fff":sub,fontSize:13,fontWeight:600,cursor:"pointer",fontFamily:"inherit",transition:"all 0.15s"}}>{p}</button>)}</div></div><div style={{marginBottom:18}}><div style={{fontSize:11,color:sub,marginBottom:6,fontWeight:600}}>REPEAT</div><div style={{display:"flex",gap:8}}>{["none","daily","weekly"].map(r=><button key={r} onClick={()=>setForm(f=>({...f,repeat:r}))} style={{flex:1,padding:"8px 0",borderRadius:10,border:`1.5px solid ${form.repeat===r?"#6C8EBF":inputBorder}`,background:form.repeat===r?"#6C8EBF":inputBg,color:form.repeat===r?"#fff":sub,fontSize:13,fontWeight:600,cursor:"pointer",fontFamily:"inherit",transition:"all 0.15s",textTransform:"capitalize"}}>{r==="none"?"Once":r}</button>)}</div></div><div style={{display:"flex",gap:8}}><button onClick={()=>setModal(null)} style={{flex:1,padding:"11px 0",borderRadius:10,border:`1.5px solid ${inputBorder}`,background:inputBg,color:sub,fontSize:14,cursor:"pointer",fontFamily:"inherit"}}>Cancel</button><button onClick={()=>addTask(modal.date)} style={{flex:2,padding:"11px 0",borderRadius:10,border:"none",background:"#6C8EBF",color:"#fff",fontSize:14,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Add Task</button></div></div></div>)}

      {manageOpen&&(<div style={{position:"fixed",inset:0,background:"rgba(0,0,0,0.35)",display:"flex",alignItems:"center",justifyContent:"center",zIndex:100,padding:16}}><div style={{background:card,borderRadius:20,padding:28,width:"100%",maxWidth:420,boxShadow:"0 8px 40px rgba(0,0,0,0.2)",animation:"slideUp 0.25s ease",maxHeight:"80vh",overflowY:"auto"}}><div style={{fontSize:17,fontWeight:700,marginBottom:4,color:text}}>↻ Repeating Tasks</div><div style={{fontSize:12,color:sub,marginBottom:18}}>Disable or delete recurring tasks here.</div>{recurringTasks.length===0&&<div style={{fontSize:13,color:sub,textAlign:"center",padding:"20px 0"}}>No repeating tasks yet.</div>}{recurringTasks.map(t=>(<div key={t.id} style={{display:"flex",alignItems:"center",gap:10,padding:"10px 12px",background:dayBg,borderRadius:10,marginBottom:8,border:`1px solid ${cardBorder}`}}><div style={{flex:1,minWidth:0}}><div style={{fontSize:13.5,fontWeight:500,color:t.disabledFrom?sub:text,textDecoration:t.disabledFrom?"line-through":"none"}}>{t.title}</div><div style={{fontSize:11,color:sub,marginTop:2}}><span style={{color:"#6C8EBF",fontWeight:600,textTransform:"capitalize"}}>{t.repeat}</span> · from {t.start_date}{t.disabledFrom?` · stopped ${t.disabledFrom}`:""}</div></div>{!t.disabledFrom?<button onClick={()=>disableRecurring(t.id,todayKey)} style={{padding:"5px 10px",borderRadius:8,border:`1.5px solid ${inputBorder}`,background:inputBg,color:sub,fontSize:12,cursor:"pointer",fontFamily:"inherit",whiteSpace:"nowrap"}}>Stop</button>:<button onClick={()=>setRecurringTasks(ts=>ts.map(rt=>rt.id===t.id?{...rt,disabledFrom:undefined}:rt))} style={{padding:"5px 10px",borderRadius:8,border:"1.5px solid #6C8EBF",background:inputBg,color:"#6C8EBF",fontSize:12,cursor:"pointer",fontFamily:"inherit",whiteSpace:"nowrap"}}>Resume</button>}<div onClick={()=>deleteRecurring(t.id)} style={{cursor:"pointer",color:dark?"#3a3a5a":"#ccc",fontSize:18,lineHeight:1,padding:4}}>×</div></div>))}<button onClick={()=>setManageOpen(false)} style={{width:"100%",marginTop:8,padding:"11px 0",borderRadius:10,border:`1.5px solid ${inputBorder}`,background:inputBg,color:sub,fontSize:14,cursor:"pointer",fontFamily:"inherit"}}>Close</button></div></div>)}

      {settingsOpen&&(<div style={{position:"fixed",inset:0,background:"rgba(0,0,0,0.35)",display:"flex",alignItems:"center",justifyContent:"center",zIndex:100,padding:16}}><div style={{background:card,borderRadius:20,padding:28,width:"100%",maxWidth:400,boxShadow:"0 8px 40px rgba(0,0,0,0.2)",animation:"slideUp 0.25s ease"}}><div style={{fontSize:17,fontWeight:700,marginBottom:24,color:text}}>Settings</div><div style={{fontSize:11,color:sub,fontWeight:600,textTransform:"uppercase",letterSpacing:1,marginBottom:10}}>Account</div><input placeholder="Name" value={settingsForm.name} onChange={e=>setSettingsForm(f=>({...f,name:e.target.value}))} style={{...modalInput,marginBottom:10}}/><input placeholder="Email address" value={settingsForm.email} onChange={e=>setSettingsForm(f=>({...f,email:e.target.value}))} style={{...modalInput,marginBottom:20}}/><div style={{fontSize:11,color:sub,fontWeight:600,textTransform:"uppercase",letterSpacing:1,marginBottom:10}}>Appearance</div><div style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"12px 14px",borderRadius:10,border:`1.5px solid ${inputBorder}`,marginBottom:20}}><div style={{fontSize:14,color:text}}>Dark Mode</div><div onClick={()=>setDark(d=>!d)} style={{width:44,height:24,borderRadius:12,background:dark?"#6C8EBF":"#ddd",cursor:"pointer",position:"relative",transition:"background 0.25s"}}><div style={{position:"absolute",top:3,left:dark?23:3,width:18,height:18,borderRadius:"50%",background:"#fff",transition:"left 0.25s",boxShadow:"0 1px 4px rgba(0,0,0,0.2)"}}/></div></div><div style={{fontSize:11,color:sub,fontWeight:600,textTransform:"uppercase",letterSpacing:1,marginBottom:10}}>Other</div><button onClick={()=>{setSettingsOpen(false);localStorage.removeItem("onboarded");window.location.reload();}} style={{width:"100%",padding:"11px 0",borderRadius:10,border:`1.5px solid ${inputBorder}`,background:inputBg,color:text,fontSize:14,cursor:"pointer",fontFamily:"inherit",marginBottom:20}}>View Onboarding</button>{settingsSaved&&<div style={{fontSize:13,color:"#82B366",fontWeight:600,marginBottom:12}}>✓ Changes saved</div>}<div style={{display:"flex",gap:8}}><button onClick={()=>{setSettingsOpen(false);setSettingsSaved(false);}} style={{flex:1,padding:"11px 0",borderRadius:10,border:`1.5px solid ${inputBorder}`,background:inputBg,color:sub,fontSize:14,cursor:"pointer",fontFamily:"inherit"}}>Cancel</button><button onClick={saveSettings} style={{flex:2,padding:"11px 0",borderRadius:10,border:"none",background:"#6C8EBF",color:"#fff",fontSize:14,fontWeight:700,cursor:"pointer",fontFamily:"inherit"}}>Save Changes</button></div></div></div>)}

      {aiOpen&&(<div style={{position:"fixed",inset:0,background:"rgba(0,0,0,0.4)",display:"flex",alignItems:"center",justifyContent:"center",zIndex:100,padding:16}}><div style={{background:card,borderRadius:20,padding:28,width:"100%",maxWidth:480,boxShadow:"0 8px 40px rgba(0,0,0,0.25)",animation:"slideUp 0.25s ease"}}><div style={{fontSize:20,fontWeight:800,background:"linear-gradient(135deg,#6C8EBF,#9B59B6)",WebkitBackgroundClip:"text",WebkitTextFillColor:"transparent",marginBottom:6}}>✦ AI Planner</div><div style={{fontSize:13,color:sub,marginBottom:16}}>Describe your week or month in plain English and I'll add everything to your calendar.</div><textarea placeholder={`e.g. "Math test on the 15th, essay due the 22nd"`} value={aiInput} onChange={e=>setAiInput(e.target.value)} rows={5} style={{width:"100%",padding:"12px 14px",borderRadius:12,border:`1.5px solid ${inputBorder}`,fontSize:13.5,outline:"none",boxSizing:"border-box",fontFamily:"inherit",background:inputBg,color:text,resize:"none",lineHeight:1.6}}/>{aiMsg&&<div style={{fontSize:13,color:aiMsg.startsWith("✓")?"#82B366":"#E07070",marginTop:10,fontWeight:600}}>{aiMsg}</div>}<div style={{display:"flex",gap:8,marginTop:14}}><button onClick={()=>{setAiOpen(false);setAiMsg("");setAiInput("");}} style={{flex:1,padding:"11px 0",borderRadius:10,border:`1.5px solid ${inputBorder}`,background:inputBg,color:sub,fontSize:14,cursor:"pointer",fontFamily:"inherit"}}>Cancel</button><button onClick={handleAiSubmit} disabled={aiLoading} style={{flex:2,padding:"11px 0",borderRadius:10,border:"none",background:"linear-gradient(135deg,#6C8EBF,#9B59B6)",color:"#fff",fontSize:14,fontWeight:700,cursor:aiLoading?"not-allowed":"pointer",fontFamily:"inherit",opacity:aiLoading?0.7:1}}>{aiLoading?"Planning...":"Add to Planner"}</button></div></div></div>)}
    </div>
  );
}