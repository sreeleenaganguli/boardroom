import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { QueryClient, QueryClientProvider, useQuery, useMutation } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import {
  BarChart3, Database, ShieldCheck, Sparkles, FileText, History, LayoutDashboard, Upload, Search,
  LogOut, ChevronDown, Download, Activity, AlertTriangle, Target,
  ArrowRight, CheckCircle2, X, Shield,
} from "lucide-react";
import "./styles.css";
import "./analysis.css";
import "./chat.css";
import "./executive.css";
import "./deep-dive.css";
import "./schema.css";
import "./premium.css";
import "./polish.css";
import "./brand-theme.css";
import "./brand-fixes.css";

const queryClient = new QueryClient();
const API = "";
const CHART_COLORS = { primary: "#003049", secondary: "#F77F00", positive: "#003049", negative: "#D62828", highlight: "#FCBF49", critical: "#E0003C", area: "#EAE2B7" };

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem("boardroom_token");
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail || "Request failed");
  }
  return response.json();
}

type Dataset = { id: string; name: string; file_type: string; row_count: number; status: string; workspace_id: string };
type Workspace = { id: string; name: string; slug: string };
type User = { id: string; email: string; full_name: string; is_superuser: boolean; permissions: string[] };

function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    if (!localStorage.getItem("boardroom_token")) { setLoading(false); return; }
    api<User>("/api/v1/auth/me").then(setUser).catch(() => localStorage.removeItem("boardroom_token")).finally(() => setLoading(false));
  }, []);
  return { user, loading };
}

function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("admin@boardroom.local");
  const [password, setPassword] = useState("admin123");
  const [error, setError] = useState("");
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      const result = await fetch("/api/v1/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) }).then(async r => {
        const body = await r.json();
        if (!r.ok) throw new Error(body.detail);
        return body;
      });
      localStorage.setItem("boardroom_token", result.access_token);
      navigate("/");
      window.location.reload();
    } catch (err) { setError(err instanceof Error ? err.message : "Login failed"); }
  };
  return <main className="login-page">
    <section className="login-card">
      <div className="brand-mark"><BarChart3 /></div>
      <p className="eyebrow">BOARDROOM</p>
      <h1>Analytics Copilot</h1>
      <p className="muted">Sign in to access your governed intelligence workspace.</p>
      <form onSubmit={submit}>
        <label>Email<input value={email} onChange={e => setEmail(e.target.value)} type="email" /></label>
        <label>Password<input value={password} onChange={e => setPassword(e.target.value)} type="password" /></label>
        {error && <div className="error">{error}</div>}
        <button className="primary" type="submit">Sign in</button>
      </form>
    </section>
  </main>;
}

const nav = [
  { path: "/", label: "Decision Center", icon: LayoutDashboard },
  { path: "/executive", label: "Executive Report", icon: Target },
  { path: "/analytics", label: "Analytics", icon: BarChart3 },
  { path: "/data", label: "Data Workspace", icon: Database },
  { path: "/schema", label: "Schema Approval", icon: ShieldCheck },
  { path: "/health", label: "Data Health", icon: ShieldCheck },
  { path: "/ask", label: "Ask Analytics", icon: Sparkles },
  { path: "/reports", label: "Report Studio", icon: FileText },
  { path: "/runs", label: "Run History", icon: History },
];

function Shell({ user }: { user: User }) {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const workspace = useQuery({ queryKey: ["workspaces"], queryFn: () => api<Workspace[]>("/api/v1/workspaces") });
  return <div className="app-shell">
    <aside className={sidebarOpen ? "sidebar" : "sidebar collapsed"}>
      <div className="brand"><div className="brand-mark small"><BarChart3 /></div>{sidebarOpen && <div><strong>Boardroom</strong><span>Analytics Copilot</span></div>}</div>
      <nav>{nav.map(({ path, label, icon: Icon }) => <NavLink key={path} to={path} end={path === "/"} className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}><Icon size={18}/>{sidebarOpen && <span>{label}</span>}</NavLink>)}</nav>
      <button className="collapse" onClick={() => setSidebarOpen(v => !v)}>‹</button>
    </aside>
    <div className="main">
      <header>
        <button className="workspace-select"><span>{workspace.data?.[0]?.name || "Workspace"}</span><ChevronDown size={16}/></button>
        <div className="header-actions"><div className="avatar">{user.full_name.slice(0, 1)}</div><div><strong>{user.full_name}</strong><span>{user.is_superuser ? "Super Administrator" : "Workspace Member"}</span></div><button className="icon-button" title="Sign out" onClick={() => { localStorage.removeItem("boardroom_token"); window.location.reload(); }}><LogOut size={17}/></button></div>
      </header>
      <Routes>
        <Route path="/" element={<ExecutiveDecision workspaceId={workspace.data?.[0]?.id} view="decision"/>} />
        <Route path="/executive" element={<ExecutiveDecision workspaceId={workspace.data?.[0]?.id} view="report"/>} />
        <Route path="/analytics" element={<AnalyticalDeepDive workspaceId={workspace.data?.[0]?.id}/>} />
        <Route path="/data" element={<DataWorkspace workspaceId={workspace.data?.[0]?.id}/>} />
        <Route path="/schema" element={<SchemaApproval workspaceId={workspace.data?.[0]?.id}/>} />
        <Route path="/health" element={<DataHealth workspaceId={workspace.data?.[0]?.id}/>} />
        <Route path="/ask" element={<AskAnalytics workspaceId={workspace.data?.[0]?.id} user={user}/>} />
        <Route path="/reports" element={<Reports workspaceId={workspace.data?.[0]?.id}/>} />
        <Route path="/runs" element={<Runs workspaceId={workspace.data?.[0]?.id}/>} />
        <Route path="*" element={<ExecutiveDecision workspaceId={workspace.data?.[0]?.id} view="decision"/>} />
      </Routes>
    </div>
  </div>;
}

function Page({ title, subtitle, action, children }: { title: string; subtitle: string; action?: React.ReactNode; children: React.ReactNode }) {
  return <section className="page"><div className="page-head"><div><p className="eyebrow">BOARDROOM WORKSPACE</p><h1>{title}</h1><p>{subtitle}</p></div>{action}</div>{children}</section>;
}

const displayValue=(value:number, unit:string)=>unit==="percent"?`${value.toFixed(1)}%`:unit==="currency"?new Intl.NumberFormat(undefined,{maximumFractionDigits:0}).format(value):new Intl.NumberFormat().format(value);

async function downloadExecutiveReport(datasetId:string, format:"markdown"|"pdf") {
  const token=localStorage.getItem("boardroom_token");
  const response=await fetch(`/api/v1/executive/datasets/${datasetId}/export?format=${format}`,{headers:token?{Authorization:`Bearer ${token}`}:{}});
  if(!response.ok) throw new Error("Executive report export failed");
  const url=URL.createObjectURL(await response.blob()); const anchor=document.createElement("a");
  anchor.href=url; anchor.download=`executive-decision-report.${format==="pdf"?"pdf":"md"}`; anchor.click(); window.setTimeout(()=>URL.revokeObjectURL(url),1000);
}

function ExecutiveDecision({ workspaceId, view }: { workspaceId?: string; view: "decision" | "report" }) {
  const datasets=useQuery({queryKey:["executive-datasets",workspaceId],queryFn:()=>api<Dataset[]>(`/api/v1/datasets${workspaceId?`?workspace_id=${workspaceId}`:""}`)});
  const [datasetId,setDatasetId]=useState("");
  const effective=datasetId||datasets.data?.[0]?.id;
  const report=useQuery({queryKey:["executive-analysis",effective],enabled:!!effective,queryFn:()=>api<any>(`/api/v1/executive/datasets/${effective}`)});
  const [scenarioMetric,setScenarioMetric]=useState(""); const [scenarioChange,setScenarioChange]=useState(5);
  const [exportError,setExportError]=useState("");
  const [evidenceOpen,setEvidenceOpen]=useState(false);
  const scenario=useMutation({mutationFn:()=>api<any>("/api/v1/executive/scenario",{method:"POST",body:JSON.stringify({dataset_id:effective,metric_key:scenarioMetric||report.data?.kpis?.[0]?.key,change_percent:scenarioChange})})});
  const data=report.data;
  const trendOption=data?.trend?.length?{color:[CHART_COLORS.primary,CHART_COLORS.secondary,CHART_COLORS.positive],tooltip:{trigger:"axis",valueFormatter:(v:number)=>v.toLocaleString()},grid:{left:58,right:26,top:25,bottom:42},xAxis:{type:"category",name:"Month",data:data.trend.map((x:any)=>x.period)},yAxis:{type:"value",name:"Value"},series:[{name:"Verified revenue",type:"line",smooth:true,data:data.trend.map((x:any)=>x.value),areaStyle:{color:CHART_COLORS.area},lineStyle:{color:CHART_COLORS.primary,width:3},itemStyle:{color:CHART_COLORS.primary}}]}:null;
  return <Page title={view==="report"?"Executive Report":"Leadership Decision Center"} subtitle={view==="report"?"A presentation-ready narrative with supporting evidence":"Prioritized risks, opportunities, and leadership actions"} action={datasets.data?.length?<div className="executive-actions"><label>Dataset<select value={effective||""} onChange={e=>{setDatasetId(e.target.value);scenario.reset();}}>{datasets.data.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label><button className="secondary" onClick={()=>effective&&downloadExecutiveReport(effective,"markdown").catch(e=>setExportError(e.message))}><Download size={15}/> Markdown</button><button className="primary" onClick={()=>effective&&downloadExecutiveReport(effective,"pdf").catch(e=>setExportError(e.message))}><Download size={15}/> PDF</button></div>:undefined}>
    {exportError&&<div className="error">{exportError}</div>}
    {!datasets.isLoading&&!datasets.data?.length&&<div className="empty">Upload a CSV or SQLite dataset in Data Workspace to generate an executive briefing.</div>}
    {report.isLoading&&<div className="empty">Calculating verified KPIs, changes, and risk signals…</div>}
    {report.isError&&<div className="error">{report.error.message}</div>}
    {data&&<>
      <article className={`executive-hero boardroom-signal ${view}`}><div className="signal-copy"><span className="eyebrow">{view==="decision"?"BOARDROOM SIGNAL":"EXECUTIVE BRIEFING"} · {data.dataset.domain}</span><h2>{view==="report"?"The leadership narrative, backed by evidence.":"What leadership should know now."}</h2><p>{view==="report"?data.briefing:(data.alerts.length?`${data.alerts[0].title}: ${data.alerts[0].detail}`:data.briefing)}</p><div className="signal-actions"><button className="evidence-button" onClick={()=>setEvidenceOpen(true)}><Shield size={15}/> Show evidence <ArrowRight size={14}/></button><span>{data.dataset.records.toLocaleString()} records · {data.quality.status}{data.quality.score!==null?` ${data.quality.score.toFixed(0)}%`:""} reliable</span></div></div><div className="signal-priorities">{view==="decision"&&<><div className="priority-tile risk"><small>URGENT SIGNAL</small><strong>{data.alerts[0]?.title||"No critical risk detected"}</strong><span>{data.alerts[0]?.severity||"Informational"}</span></div><div className="priority-tile opportunity"><small>RECOMMENDED ACTION</small><strong>{data.evidence[1]?.title||"Review verified KPIs"}</strong><span>Open evidence before acting</span></div></>}<div className="health-orb"><strong>{data.health.score===null?"—":data.health.score}</strong><span>Business health</span><small>Only applicable dimensions</small></div></div></article>
      <div className="stat-grid executive-kpis">{data.kpis.slice(0,6).map((k:any)=><article className="stat-card" key={k.key}><span>{k.label}</span><strong>{displayValue(k.value,k.unit)}</strong>{k.change_percent!==undefined&&<small className={k.change_percent>=0?"positive":"negative"}>{k.change_percent>=0?"▲":"▼"} {Math.abs(k.change_percent).toFixed(1)}% vs prior period</small>}<small title={k.calculation}>Evidence: {k.calculation}</small></article>)}</div>
      <div className="grid-two executive-grid"><article className="panel"><div className="panel-head"><div><h2>Performance trend</h2><p>Verified monthly aggregation; use filters in Ask Analytics for deeper cuts.</p></div><Activity size={18}/></div>{trendOption?<ReactECharts option={trendOption} style={{height:300}}/>:<div className="empty">A revenue measure and valid date column are required for a trend.</div>}</article>
      <article className="panel"><div className="panel-head"><div><h2>Health methodology</h2><p>Performance and reliability are deliberately distinct.</p></div></div>{data.health.dimensions.length?<div className="health-list">{data.health.dimensions.map((d:any)=><div key={d.name}><div><strong>{d.name}</strong><span>{d.score.toFixed(1)} / 100</span></div><div className="meter"><i style={{width:`${d.score}%`}}/></div><small>{d.basis}</small></div>)}</div>:<div className="empty">Not enough comparable measures for a health score.</div>}</article></div>
      <div className="grid-two executive-grid"><article className="panel"><div className="panel-head"><div><h2>What changed & why</h2><p>Measured contributions, not causal claims.</p></div></div><div className="evidence-list">{data.evidence.slice(0,4).map((item:any,i:number)=><details key={i} open={i===0}><summary><span className={`evidence-type ${item.type.replace(" ","-").toLowerCase()}`}>{item.type}</span><strong>{item.title}</strong><span className={`severity ${item.severity}`}>{item.severity}</span></summary><p>{item.finding}</p>{item.drivers&&<div className="driver-list">{item.drivers.map((driver:any)=><span key={driver.segment}>{driver.segment}: <strong>{driver.contribution>=0?"+":""}{driver.contribution.toLocaleString()}</strong></span>)}<small>Unexplained residual: {item.residual.toLocaleString()}</small></div>}<code>{item.calculation}</code></details>)}</div></article>
      <article className="panel"><div className="panel-head"><div><h2>Risk radar</h2><p>Statistical exceptions require business investigation.</p></div><AlertTriangle size={18}/></div>{data.alerts.length?<div className="alert-list">{data.alerts.map((a:any,i:number)=><div className={`alert ${a.severity.toLowerCase()}`} key={i}><strong>{a.severity} · {a.title}</strong><span>{a.detail}</span></div>)}</div>:<div className="empty">No prioritized alerts from the available signals.</div>}<div className="anomaly-note">{data.anomalies.length?`${data.anomalies.length} measured outlier signal(s) detected using disclosed IQR baselines.`:"No IQR anomaly signals met the minimum observation threshold."}</div></article></div>
      {view==="decision"&&<div className="grid-two executive-grid"><article className="panel scenario-panel"><div className="panel-head"><div><h2>Scenario Lab</h2><p>Mathematical sensitivity, not a validated forecast.</p></div></div>{data.kpis.length?<><div className="scenario-controls"><label>KPI<select value={scenarioMetric||data.kpis[0].key} onChange={e=>setScenarioMetric(e.target.value)}>{data.kpis.map((k:any)=><option key={k.key} value={k.key}>{k.label}</option>)}</select></label><label>Assumption: {scenarioChange}%<input type="range" min="-30" max="30" value={scenarioChange} onChange={e=>setScenarioChange(+e.target.value)}/></label><button className="primary" onClick={()=>scenario.mutate()} disabled={scenario.isPending}>{scenario.isPending?"Simulating…":"Run scenario"}</button></div>{scenario.data&&<div className="scenario-result"><span>Baseline <strong>{scenario.data.baseline.toLocaleString()}</strong></span><span>Simulated <strong>{scenario.data.simulated.toLocaleString()}</strong></span><span>Difference <strong>{scenario.data.difference>=0?"+":""}{scenario.data.difference.toLocaleString()}</strong></span><small>{scenario.data.assumptions}</small></div>}</>:<div className="empty">No supported KPI is available for simulation.</div>}</article>
      <article className="panel"><div className="panel-head"><div><h2>Trust & limitations</h2><p>How to read this report.</p></div></div><div className="methodology"><p>{data.methodology}</p><p><strong>Evidence trace:</strong> open any finding to review its deterministic calculation. Run Data Health to refresh the reliability component.</p><p><strong>Forecasting:</strong> unavailable unless there is sufficient validated historical data; no prediction is fabricated.</p></div></article></div>}
      {evidenceOpen&&<div className="evidence-drawer-backdrop" role="dialog" aria-modal="true" aria-label="Evidence trace"><aside className="evidence-drawer"><button className="icon-button drawer-close" onClick={()=>setEvidenceOpen(false)} aria-label="Close evidence"><X size={17}/></button><p className="eyebrow">EVIDENCE TRACE</p><h2>Every claim has a calculation.</h2><p className="muted">These are verified calculations from the approved dataset. Interpretation is kept separate from evidence.</p>{data.evidence.map((item:any,index:number)=><article className="drawer-evidence" key={index}><span className="evidence-type">{item.type}</span><h3>{item.title}</h3><p>{item.finding}</p><code>{item.calculation}</code></article>)}</aside></div>}
    </>}
  </Page>;
}

function AnalyticalDeepDive({ workspaceId }: { workspaceId?: string }) {
  const datasets=useQuery({queryKey:["deep-dive-datasets",workspaceId],queryFn:()=>api<Dataset[]>(`/api/v1/datasets${workspaceId?`?workspace_id=${workspaceId}`:""}`)});
  const [datasetId,setDatasetId]=useState(""); const effective=datasetId||datasets.data?.[0]?.id;
  const deepDive=useQuery({queryKey:["deep-dive",effective],enabled:!!effective,queryFn:()=>api<any>(`/api/v1/executive/datasets/${effective}/deep-dive`)});
  const data=deepDive.data;
  const segment=data?.segments?.[0];
  const segmentChart=segment?{color:[CHART_COLORS.secondary,CHART_COLORS.primary,CHART_COLORS.positive],tooltip:{trigger:"axis"},grid:{left:56,right:20,top:18,bottom:72},xAxis:{type:"category",data:segment.rows.map((x:any)=>x.segment),axisLabel:{rotate:segment.rows.length>6?30:0}},yAxis:{type:"value",name:segment.metric},series:[{type:"bar",data:segment.rows.map((x:any)=>x.value),itemStyle:{color:CHART_COLORS.secondary,borderRadius:[4,4,0,0]}}]}:null;
  return <Page title="Analytical Deep Dive" subtitle="Segments, distributions, correlations, and forecast readiness" action={datasets.data?.length?<label>Dataset<select value={effective||""} onChange={e=>setDatasetId(e.target.value)}>{datasets.data.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label>:undefined}>
    {!datasets.isLoading&&!datasets.data?.length&&<div className="empty">Upload a dataset to unlock analytical deep dives.</div>}
    {deepDive.isLoading&&<div className="empty">Calculating descriptive statistics and segment comparisons…</div>}
    {deepDive.isError&&<div className="error">{deepDive.error.message}</div>}
    {data&&<><div className="grid-two executive-grid"><article className="panel"><div className="panel-head"><div><h2>Segment performance</h2><p>{segment?`${segment.metric} aggregated by ${segment.dimension}`:"No compatible measure and segment are available."}</p></div></div>{segmentChart?<ReactECharts option={segmentChart} style={{height:320}}/>:<div className="empty">A numeric measure and low-cardinality category are required.</div>}</article><article className="panel"><div className="panel-head"><div><h2>Forecast readiness</h2><p>Forecasts are only produced after validation.</p></div></div><div className="methodology"><p><strong>{data.forecast.available?"Available":"Not available"}</strong></p><p>{data.forecast.reason}</p>{data.forecast.observations!==undefined&&<p>Validated monthly observations: {data.forecast.observations}</p>}</div></article></div>
      <article className="panel executive-grid"><div className="panel-head"><div><h2>Distribution & descriptive statistics</h2><p>Calculated from non-null numeric values; no imputation is applied.</p></div></div>{data.statistics.length?<table><thead><tr><th>Measure</th><th>Count</th><th>Missing</th><th>Mean</th><th>Median</th><th>Std. dev.</th><th>P25–P75</th></tr></thead><tbody>{data.statistics.map((item:any)=><tr key={item.column}><td><strong>{item.column}</strong></td><td>{item.count.toLocaleString()}</td><td>{item.missing.toLocaleString()}</td><td>{item.mean.toLocaleString(undefined,{maximumFractionDigits:2})}</td><td>{item.median.toLocaleString(undefined,{maximumFractionDigits:2})}</td><td>{item.std_dev.toLocaleString(undefined,{maximumFractionDigits:2})}</td><td>{item.p25.toLocaleString(undefined,{maximumFractionDigits:2})} – {item.p75.toLocaleString(undefined,{maximumFractionDigits:2})}</td></tr>)}</tbody></table>:<div className="empty">No numeric measures were detected.</div>}</article>
      <div className="grid-two"><article className="panel"><div className="panel-head"><div><h2>Correlation signals</h2><p>Associations to investigate, never causal evidence.</p></div></div>{data.correlations.length?<div className="evidence-list">{data.correlations.map((item:any,index:number)=><div key={index}><strong>{item.left} ↔ {item.right}</strong><span className="tag">{item.coefficient.toFixed(2)} · {item.strength}</span><p>{item.note}</p></div>)}</div>:<div className="empty">No moderate or strong paired correlations were found.</div>}</article><article className="panel"><div className="panel-head"><div><h2>Available segment cuts</h2><p>Top values are sorted by the selected business measure.</p></div></div><div className="evidence-list">{data.segments.slice(1).map((item:any)=><details key={item.dimension}><summary><strong>{item.dimension}</strong><span className="tag">{item.metric}</span></summary><table><thead><tr><th>Segment</th><th>Total</th><th>Average</th><th>Records</th></tr></thead><tbody>{item.rows.map((row:any)=><tr key={row.segment}><td>{row.segment}</td><td>{row.value.toLocaleString()}</td><td>{row.average.toLocaleString(undefined,{maximumFractionDigits:2})}</td><td>{row.records}</td></tr>)}</tbody></table></details>)}</div></article></div>
    </>}
  </Page>;
}

function Overview({ workspaceId }: { workspaceId?: string }) {
  const overview = useQuery({ queryKey: ["overview", workspaceId], queryFn: () => api<any>(`/api/v1/overview${workspaceId ? `?workspace_id=${workspaceId}` : ""}`) });
  const datasets = useQuery({ queryKey: ["datasets-overview", workspaceId], queryFn: () => api<Dataset[]>(`/api/v1/datasets${workspaceId ? `?workspace_id=${workspaceId}` : ""}`) });
  const stats = [
    ["Datasets", overview.data?.dataset_count ?? "—", "Governed sources"],
    ["Data rows", overview.data?.row_count?.toLocaleString() ?? "—", "Across active datasets"],
    ["Analytics runs", overview.data?.run_count ?? "—", `${overview.data?.completed_runs ?? 0} completed`],
    ["Executive reports", overview.data?.report_count ?? "—", "Saved review-ready outputs"],
  ];
  return <Page title="Executive Overview" subtitle="Your enterprise analytics command center">
    <div className="stat-grid">{stats.map(([label, value, note]) => <article className="stat-card" key={label}><span>{label}</span><strong>{value}</strong><small>{note}</small></article>)}</div>
    <div className="grid-two">
      <article className="panel"><div className="panel-head"><div><h2>Workspace activity</h2><p>Analytics and reporting utilization</p></div></div>
        {overview.data?.activity ? <ReactECharts option={{ color:[CHART_COLORS.primary],tooltip:{trigger:"axis"}, grid:{left:36,right:16,top:20,bottom:34}, xAxis:{type:"category",data:overview.data.activity.map((day:any)=>day.date.slice(5))}, yAxis:{type:"value",minInterval:1}, series:[{type:"bar",name:"Analytics runs",data:overview.data.activity.map((day:any)=>day.runs),itemStyle:{color:CHART_COLORS.primary},barWidth:"38%",borderRadius:[4,4,0,0]}]}} style={{height:280}} /> : <div className="empty">Loading activity…</div>}
      </article>
      <article className="panel"><div className="panel-head"><div><h2>Datasets</h2><p>Recently available sources</p></div></div>
        {datasets.isLoading ? <div className="empty">Loading datasets…</div> : datasets.data?.length ? <div className="list">{datasets.data.map(d => <div className="list-row" key={d.id}><div className="file-icon"><Database size={17}/></div><div><strong>{d.name}</strong><span>{d.row_count?.toLocaleString()} rows · {d.file_type.toUpperCase()}</span></div><span className={`status ${d.status}`}>{d.status}</span></div>)}</div> : <div className="empty">No datasets uploaded yet</div>}
      </article>
    </div>
  </Page>;
}

function DataWorkspace({ workspaceId }: { workspaceId?: string }) {
  const [selected, setSelected] = useState("");
  const datasets = useQuery({ queryKey:["datasets",workspaceId], queryFn:()=>api<Dataset[]>(`/api/v1/datasets${workspaceId ? `?workspace_id=${workspaceId}` : ""}`) });
  const upload = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData(); form.append("file", file);
      return api<{id:string}>(`/api/v1/datasets/upload?workspace_id=${workspaceId}`, {method:"POST", body:form});
    },
    onSuccess:()=>datasets.refetch(),
  });
  return <Page title="Data Workspace" subtitle="Upload, inspect and govern analytical datasets" action={<label className="primary upload-label"><Upload size={16}/> Upload data<input type="file" accept=".csv,.sqlite,.sqlite3,.db" onChange={e=>{if(e.target.files?.[0]) upload.mutate(e.target.files[0]);}} /></label>}>
    {upload.isError && <div className="error">{upload.error.message}</div>}
    {upload.isSuccess && <div className="success">Dataset uploaded and profiled successfully.</div>}
    <article className="panel"><div className="panel-head"><div><h2>Datasets</h2><p>{datasets.data?.length || 0} sources in this workspace</p></div></div>
      {datasets.isLoading ? <div className="empty">Loading…</div> : datasets.data?.length ? <table><thead><tr><th>Name</th><th>Type</th><th>Rows</th><th>Status</th><th></th></tr></thead><tbody>{datasets.data.map(d=><tr key={d.id} className={selected===d.id?"selected":""} onClick={()=>setSelected(d.id)}><td><strong>{d.name}</strong></td><td>{d.file_type.toUpperCase()}</td><td>{d.row_count?.toLocaleString()}</td><td><span className={`status ${d.status}`}>{d.status}</span></td><td><button className="icon-button" title="Select dataset"><Search size={15}/></button></td></tr>)}</tbody></table> : <div className="drop-zone"><Upload/><strong>Upload a CSV or SQLite file</strong><span>Schema profiling starts automatically</span></div>}
    </article>
  </Page>;
}

function SchemaApproval({ workspaceId }: { workspaceId?: string }) {
  const datasets=useQuery({queryKey:["schema-approval-datasets",workspaceId],queryFn:()=>api<Dataset[]>(`/api/v1/datasets${workspaceId?`?workspace_id=${workspaceId}`:""}`)});
  const [datasetId,setDatasetId]=useState(""); const effective=datasetId||datasets.data?.[0]?.id;
  const approval=useQuery({queryKey:["schema-approval",effective],enabled:!!effective,queryFn:()=>api<any>(`/api/v1/schema/datasets/${effective}/approval`)});
  const [columns,setColumns]=useState<any[]>([]); const [domain,setDomain]=useState(""); const [dateColumn,setDateColumn]=useState("");
  useEffect(()=>{if(approval.data){setColumns(approval.data.columns);setDomain(approval.data.domain||"");setDateColumn(approval.data.primary_date_column||"");}},[approval.data]);
  const save=useMutation({mutationFn:()=>api<any>(`/api/v1/schema/datasets/${effective}/approval`,{method:"POST",body:JSON.stringify({columns,domain,primary_date_column:dateColumn||null})}),onSuccess:()=>{approval.refetch();queryClient.invalidateQueries({queryKey:["schema",effective]});}});
  const update=(index:number,field:string,value:any)=>setColumns(current=>current.map((column,i)=>i===index?{...column,[field]:value}:column));
  return <Page title="Data Contract" subtitle="Approve the business meaning of raw data before executive analysis" action={datasets.data?.length?<label>Dataset<select value={effective||""} onChange={e=>setDatasetId(e.target.value)}>{datasets.data.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label>:undefined}>
    {!datasets.isLoading&&!datasets.data?.length&&<div className="empty">Upload a CSV or SQLite dataset to start schema approval.</div>}
    {approval.isLoading&&<div className="empty">Profiling inferred business meaning…</div>}
    {approval.isError&&<div className="error">{approval.error.message}</div>}
    {approval.data&&<><article className="executive-hero schema-hero"><div><span className="eyebrow">{approval.data.status==="approved"?`Approved contract v${approval.data.version}`:"Approval required"}</span><h2>{approval.data.domain}</h2><p>Review the inferred roles, then approve the business contract. Raw source data remains unchanged; approval controls how analysis interprets it.</p></div><div className="health-orb"><strong>{approval.data.readiness.filter((x:any)=>x.ready).length}/4</strong><span>Use cases ready</span></div></article>
      <div className="stat-grid executive-kpis">{approval.data.readiness.map((item:any)=><article className="stat-card" key={item.use_case}><span>{item.use_case}</span><strong>{item.score}%</strong><small className={item.ready?"positive":"negative"}>{item.ready?"Ready after approval":"Needs fields or validation"}</small><small>{item.reason}</small></article>)}</div>
      <div className="grid-two executive-grid"><article className="panel"><div className="panel-head"><div><h2>Business settings</h2><p>These choices define time comparisons and domain-aware KPIs.</p></div></div><div className="schema-settings"><label>Business domain<input value={domain} onChange={e=>setDomain(e.target.value)} placeholder="E-commerce, SaaS, finance…"/></label><label>Primary reporting date<select value={dateColumn} onChange={e=>setDateColumn(e.target.value)}><option value="">No approved date column</option>{columns.filter(c=>c.role==="time").map(c=><option value={c.column_name} key={c.column_name}>{c.column_name}</option>)}</select></label></div></article><article className="panel"><div className="panel-head"><div><h2>Governance promise</h2><p>What approval changes.</p></div></div><div className="methodology"><p><strong>Raw files are immutable.</strong> This contract stores business meaning, not a destructive data rewrite.</p><p>Sensitive fields can be excluded from reports, AI prompts, and exports.</p><p>Each approval creates a versioned, auditable contract.</p></div></article></div>
      <article className="panel"><div className="panel-head"><div><h2>Explainable field mapping</h2><p>Every suggestion includes the observed reason. Set a role, include it, then approve.</p></div><button className="primary" onClick={()=>save.mutate()} disabled={save.isPending}>{save.isPending?"Approving…":"Approve schema"}</button></div>{save.isError&&<div className="error">{save.error.message}</div>}{save.isSuccess&&<div className="success">Schema contract v{save.data.version} approved. Reporting will use the approved field roles.</div>}<table className="schema-table"><thead><tr><th>Source column</th><th>Role</th><th>Include</th><th>Sensitive</th><th>Why this was inferred</th><th>Coverage</th></tr></thead><tbody>{columns.map((column,index)=><tr key={column.column_name}><td><strong>{column.column_name}</strong><small>{column.data_type}</small></td><td><select value={column.role} onChange={e=>update(index,"role",e.target.value)}><option value="time">Time</option><option value="revenue">Revenue</option><option value="measure">Measure</option><option value="dimension">Dimension</option><option value="identifier">Identifier</option><option value="sensitive">Sensitive</option><option value="ignored">Ignore</option></select></td><td><input type="checkbox" checked={column.include} onChange={e=>update(index,"include",e.target.checked)}/></td><td><input type="checkbox" checked={column.is_pii} onChange={e=>update(index,"is_pii",e.target.checked)}/></td><td>{column.reason}</td><td>{(column.unique_count??0).toLocaleString()} distinct<br/>{(column.null_count??0).toLocaleString()} missing</td></tr>)}</tbody></table></article>
    </>}
  </Page>;
}

function DataHealth({ workspaceId }: { workspaceId?: string }) {
  const datasets = useQuery({ queryKey:["health-datasets",workspaceId],queryFn:()=>api<Dataset[]>(`/api/v1/datasets${workspaceId ? `?workspace_id=${workspaceId}` : ""}`) });
  const [datasetId,setDatasetId]=useState("");
  const effective=datasetId || datasets.data?.[0]?.id;
  const schema=useQuery({queryKey:["schema",effective],enabled:!!effective,queryFn:()=>api<any[]>(`/api/v1/schema/datasets/${effective}`)});
  const report=useQuery({queryKey:["quality",effective],enabled:!!effective,queryFn:()=>api<any>(`/api/v1/quality/datasets/${effective}`).catch(()=>null)});
  const scan=useMutation({mutationFn:()=>api<any>(`/api/v1/quality/datasets/${effective}/scan`,{method:"POST"}),onSuccess:()=>report.refetch()});
  return <Page title="Data Confidence" subtitle="Know which conclusions are reliable before leadership acts" action={effective?<button className="primary" onClick={()=>scan.mutate()} disabled={scan.isPending}>Refresh confidence scan</button>:undefined}>
    {datasets.data?.length ? <div className="toolbar"><label>Dataset<select value={effective} onChange={e=>setDatasetId(e.target.value)}>{datasets.data.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label></div>:<div className="empty">Upload a dataset to begin.</div>}
    {scan.isError&&<div className="error">{scan.error.message}</div>}
    {report.data && <div className="stat-grid three"><article className="stat-card"><span>Overall health</span><strong>{report.data.overall_score}%</strong></article><article className="stat-card"><span>Completeness</span><strong>{report.data.completeness_score}%</strong></article><article className="stat-card"><span>Consistency</span><strong>{report.data.consistency_score}%</strong></article></div>}
    <article className="panel"><div className="panel-head"><h2>Inferred schema</h2></div>{schema.data?.length?<table><thead><tr><th>Column</th><th>Data type</th><th>Semantic type</th><th>Unique</th><th>Missing</th></tr></thead><tbody>{schema.data.map(c=><tr key={c.id}><td><strong>{c.column_name}</strong></td><td>{c.data_type}</td><td><span className="tag">{c.semantic_type}</span></td><td>{c.unique_count ?? "—"}</td><td>{c.null_count ?? "—"}</td></tr>)}</tbody></table>:<div className="empty">No schema data available</div>}</article>
  </Page>;
}

function analysisChartOption(chart: any) {
  if (!chart) return null;
  const isScatter = chart.type === "scatter";
  return {
    tooltip: { trigger: "axis" },
    grid: { left: 48, right: 24, top: 24, bottom: 56 },
    xAxis: isScatter
      ? { type: "value", name: chart.x_key, nameLocation: "middle", nameGap: 32 }
      : { type: "category", name: chart.x_key, data: chart.data.map((point: any) => point.x), axisLabel: { rotate: chart.data.length > 8 ? 30 : 0 } },
    yAxis: { type: "value", name: chart.y_key },
    series: [{
      type: chart.type,
      name: chart.y_key,
      data: isScatter ? chart.data.map((point: any) => [point.x, point.y]) : chart.data.map((point: any) => point.y),
      smooth: chart.type === "line",
      itemStyle: { color: CHART_COLORS.primary },
      areaStyle: chart.type === "line" ? { color: CHART_COLORS.area } : undefined,
    }],
  };
}

function AskAnalytics({ workspaceId, user }: { workspaceId?: string; user: User }) {
  const datasets=useQuery({queryKey:["ask-datasets",workspaceId],queryFn:()=>api<Dataset[]>(`/api/v1/datasets${workspaceId?`?workspace_id=${workspaceId}`:""}`)});
  const conversations=useQuery({
    queryKey:["conversations",workspaceId],
    enabled:!!workspaceId,
    queryFn:()=>api<any[]>(`/api/v1/conversations?workspace_id=${workspaceId}`),
  });
  const [datasetId,setDatasetId]=useState("");
  const [conversationId,setConversationId]=useState("");
  const [historyInitialized,setHistoryInitialized]=useState(false);
  const [question,setQuestion]=useState("");
  const [exportError,setExportError]=useState("");
  const effective=datasetId||datasets.data?.[0]?.id;
  useEffect(()=>{
    if(!historyInitialized&&conversations.isSuccess){
      const newest=conversations.data?.[0];
      if(newest){
        setConversationId(newest.id);
        setDatasetId(newest.dataset_id);
      }
      setHistoryInitialized(true);
    }
  },[conversations.data,conversations.isSuccess,historyInitialized]);
  const conversation=useQuery({
    queryKey:["conversation",conversationId],
    enabled:!!conversationId,
    queryFn:()=>api<any>(`/api/v1/conversations/${conversationId}`),
  });
  const canSelectModel=user.is_superuser||user.permissions.includes("model:select");
  const canCreateReport=user.is_superuser||(
    user.permissions.includes("report:create")&&user.permissions.includes("model:select")
  );
  const models=useQuery({
    queryKey:["models"],
    enabled:canSelectModel,
    queryFn:()=>api<any[]>("/api/v1/models"),
  });
  const availableModels=models.data?.filter(model=>model.configured)||[];
  const [modelId,setModelId]=useState("");
  const selectedModelId=availableModels.some(model=>model.id===modelId)?modelId:availableModels[0]?.id||"";
  const execute=useMutation({
    mutationFn:({text,existingConversationId}:{text:string;existingConversationId:string})=>api<any>("/api/v1/analytics/query",{
      method:"POST",
      body:JSON.stringify({
        workspace_id:workspaceId,
        dataset_id:effective,
        question:text,
        conversation_id:existingConversationId||undefined,
      }),
    }),
    onSuccess:result=>{
      setConversationId(result.conversation_id);
      queryClient.invalidateQueries({queryKey:["conversations",workspaceId]});
      queryClient.invalidateQueries({queryKey:["conversation",result.conversation_id]});
    },
  });
  const generateReport=useMutation({
    mutationFn:({sourceConversationId,messageId}:{sourceConversationId:string;messageId:string})=>api<any>("/api/v1/reports/generate",{
      method:"POST",
      body:JSON.stringify({
        conversation_id:sourceConversationId,
        message_id:messageId,
        model_id:selectedModelId,
      }),
    }),
    onSuccess:()=>queryClient.invalidateQueries({queryKey:["reports",workspaceId]}),
  });
  const messages=conversation.data?.messages||[];
  const ask=()=>execute.mutate({text:question,existingConversationId:conversationId});
  const startConversation=()=>{
    setConversationId("");
    setHistoryInitialized(true);
    setQuestion("");
    execute.reset();
    generateReport.reset();
  };
  const selectConversation=(id:string)=>{
    setConversationId(id);
    setQuestion("");
    execute.reset();
    generateReport.reset();
    const item=conversations.data?.find(item=>item.id===id);
    if(item) setDatasetId(item.dataset_id);
  };
  return <Page title="Ask a Verified Question" subtitle="Every answer is constrained by your approved dataset and read-only calculations">
    <div className="ask-layout"><aside className="panel ask-context"><div className="panel-head"><h2>Context</h2><button className="secondary" onClick={startConversation}>New chat</button></div><label>Dataset<select value={effective||""} onChange={e=>{setDatasetId(e.target.value);setConversationId("");execute.reset();}}>{datasets.data?.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
      {canSelectModel&&<label>Report model<select value={selectedModelId} onChange={e=>setModelId(e.target.value)} disabled={!availableModels.length}><option value="">{availableModels.length?"Select a model":"No configured model"}</option>{availableModels.map(model=><option key={model.id} value={model.id}>{model.display_name} · {model.provider}</option>)}</select>{models.isError&&<small className="error">{models.error.message}</small>}</label>}
      <div className="suggestions"><span>Try asking</span><button onClick={()=>setQuestion("Show monthly net sales trend")}>Monthly sales trend</button><button onClick={()=>setQuestion("Compare net sales by region")}>Sales by region</button><button onClick={()=>setQuestion("Which products have the highest profit?")}>Top products by profit</button></div>
      <div className="conversation-list"><strong>Saved conversations</strong>{conversations.data?.length?conversations.data.map(item=><button key={item.id} className={conversationId===item.id?"active":""} onClick={()=>selectConversation(item.id)}><span>{item.title}</span><small>{item.dataset_name}</small></button>):<small>No saved conversations yet</small>}</div>
    </aside>
    <div className="ask-main"><div className="chat-history">
      {messages.map((message:any)=><article className={`chat-message ${message.role}`} key={message.id}>
        <strong>{message.role==="user"?"You":<><span className="verified-label">VERIFIED RESULT</span> Analytics Copilot</>}</strong><p>{message.content}</p>
        {message.metadata?.sql&&<details className="sql evidence-sql"><summary>Show validated SQL and execution evidence</summary><code>{message.metadata.sql}</code></details>}
        {message.metadata?.chart&&<div className="analysis-chart"><ReactECharts option={analysisChartOption(message.metadata.chart)} style={{height:320}}/></div>}
        {!!message.metadata?.outliers?.length&&<div className="outlier-callouts"><h3>Statistical outliers</h3><div className="outlier-grid">{message.metadata.outliers.map((item:any)=><div className="outlier-card" key={item.column}><strong>{item.column}</strong><span>{item.count} value(s) outside the 1.5×IQR range</span><small>Bounds {item.lower_bound.toPrecision(4)} to {item.upper_bound.toPrecision(4)} · examples {item.examples.join(", ")}</small></div>)}</div></div>}
        {message.metadata?.columns?.length>0&&<table><thead><tr>{message.metadata.columns.map((column:string)=><th key={column}>{column}</th>)}</tr></thead><tbody>{message.metadata.rows.slice(0,20).map((row:any,index:number)=><tr key={index}>{message.metadata.columns.map((column:string)=><td key={column}>{String(row[column]??"")}</td>)}</tr>)}</tbody></table>}
        {canCreateReport&&message.metadata?.run_id&&<button className="secondary" disabled={!selectedModelId||generateReport.isPending} onClick={()=>generateReport.mutate({sourceConversationId:conversationId,messageId:message.id})}>{generateReport.isPending?"Generating…":"Generate executive report"}</button>}
      </article>)}
      {!messages.length&&<div className="empty">{conversation.isLoading?"Loading saved conversation…":"Ask a question to begin a persisted analytics conversation."}</div>}
    </div>
    <article className="prompt"><textarea value={question} onChange={e=>setQuestion(e.target.value)} placeholder="Ask a question about sales, customers, or trends…" onKeyDown={e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();if(question.trim()&&!execute.isPending)ask();}}}/><button className="primary" disabled={!effective||!question.trim()||execute.isPending} onClick={ask}><Sparkles size={16}/>{execute.isPending?"Running…":"Analyze"}</button></article>
    {execute.isError&&<div className="error">{execute.error.message}</div>}
    {generateReport.isSuccess&&<div className="success">Report generated: {generateReport.data.title}
      <button className="secondary" onClick={()=>downloadReport(generateReport.data.id,"markdown").catch(e=>setExportError(e.message))}>Download Markdown</button>
      <button className="secondary" onClick={()=>downloadReport(generateReport.data.id,"pdf").catch(e=>setExportError(e.message))}>Download PDF</button>
    </div>}
    {exportError&&<div className="error">{exportError}</div>}
    {generateReport.isError&&<div className="error">{generateReport.error.message}</div>}
    </div></div>
  </Page>;
}

async function downloadReport(reportId: string, format: "markdown" | "pdf") {
  const token=localStorage.getItem("boardroom_token");
  const response=await fetch(`/api/v1/reports/${reportId}/export?format=${format}`,{headers:token?{Authorization:`Bearer ${token}`}:{}})
  if(!response.ok) throw new Error("Report export failed");
  const blob=await response.blob();
  const url=URL.createObjectURL(blob);
  const anchor=document.createElement("a");
  anchor.href=url;
  anchor.download=`boardroom-report.${format === "markdown" ? "md" : "pdf"}`;
  anchor.click();
  window.setTimeout(()=>URL.revokeObjectURL(url),1000);
}

function Reports({ workspaceId }: { workspaceId?: string }) {
  const reports=useQuery({queryKey:["reports",workspaceId],queryFn:()=>api<any[]>(`/api/v1/reports${workspaceId?`?workspace_id=${workspaceId}`:""}`)});
  const [exportError,setExportError]=useState("");
  return <Page title="Report Studio" subtitle="Review model-generated analysis grounded in saved query results">
    {exportError&&<div className="error">{exportError}</div>}
    <div className="report-list">{reports.data?.length?reports.data.map(report=><article className="panel saved-report" key={report.id}>
      <div className="panel-head"><div><h2>{report.title}</h2><p>{report.description||"Evidence-backed executive report"} · {new Date(report.created_at).toLocaleString()}</p></div><div><button className="secondary" onClick={()=>downloadReport(report.id,"markdown").catch(e=>setExportError(e.message))}><Download size={15}/> Markdown</button><button className="secondary" onClick={()=>downloadReport(report.id,"pdf").catch(e=>setExportError(e.message))}>PDF</button></div></div>
      <h3>Executive summary</h3><p className="report-summary">{report.content?.summary||"No summary was saved."}</p>
      {report.content?.question&&<p><strong>Analysis question:</strong> {report.content.question}</p>}
      {report.content?.chart&&<div className="analysis-chart"><ReactECharts option={analysisChartOption(report.content.chart)} style={{height:320}}/></div>}
      {report.content?.model&&<small>Generated with {report.content.model.name} · {report.content.model.provider}</small>}
    </article>):<div className="empty">{reports.isLoading?"Loading reports…":"No generated reports yet. Generate one from a saved Ask Analytics result."}</div>}</div>
  </Page>;
}

function Runs({ workspaceId }: { workspaceId?: string }) {
  const runs=useQuery({queryKey:["runs",workspaceId],queryFn:()=>api<any[]>(`/api/v1/runs${workspaceId?`?workspace_id=${workspaceId}`:""}`)});
  return <Page title="Run History" subtitle="Trace persisted analytics execution and reproducible SQL"><article className="panel">{runs.data?.length?<table><thead><tr><th>Question</th><th>Status</th><th>SQL</th><th>Created</th></tr></thead><tbody>{runs.data.map(r=><tr key={r.id}><td><strong>{r.question}</strong></td><td><span className={`status ${r.status}`}>{r.status}</span></td><td><code className="truncate">{r.sql}</code></td><td>{new Date(r.created_at).toLocaleString()}</td></tr>)}</tbody></table>:<div className="empty">No analytics runs yet</div>}</article></Page>;
}

function App() {
  const {user,loading}=useAuth();
  if(loading) return <main className="login-page"><div className="loading">Loading workspace…</div></main>;
  if(!user) return <Login />;
  return <Shell user={user}/>;
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><QueryClientProvider client={queryClient}><BrowserRouter><App/></BrowserRouter></QueryClientProvider></React.StrictMode>);
