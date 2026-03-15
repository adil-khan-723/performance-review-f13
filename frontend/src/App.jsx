import { useState, useEffect, createContext, useContext } from "react";
import { CognitoUserPool, CognitoUser, AuthenticationDetails } from "amazon-cognito-identity-js";

// ─── Config (filled from SAM outputs) ────────────────────────────────────────
const CONFIG = {
  apiBase: import.meta.env.VITE_API_BASE || "https://your-api-id.execute-api.us-east-1.amazonaws.com/dev",
  cognitoPoolId: import.meta.env.VITE_COGNITO_POOL_ID || "us-east-1_XXXXXXX",
  cognitoClientId: import.meta.env.VITE_COGNITO_CLIENT_ID || "XXXXXXXXXXXXXXXXXXXXXXXX",
};

const userPool = new CognitoUserPool({
  UserPoolId: CONFIG.cognitoPoolId,
  ClientId: CONFIG.cognitoClientId,
});

// ─── Auth Context ─────────────────────────────────────────────────────────────
const AuthCtx = createContext(null);
function useAuth() { return useContext(AuthCtx); }

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const cognitoUser = userPool.getCurrentUser();
    if (cognitoUser) {
      cognitoUser.getSession((err, session) => {
        if (!err && session.isValid()) {
          const payload = session.getIdToken().decodePayload();
          setToken(session.getIdToken().getJwtToken());
          setUser({
            id: payload["custom:employee_id"],
            name: payload.name || payload.email,
            email: payload.email,
            role: payload["custom:role"] || "employee",
          });
        }
        setLoading(false);
      });
    } else {
      setLoading(false);
    }
  }, []);

  const login = (email, password) =>
    new Promise((resolve, reject) => {
      const cognitoUser = new CognitoUser({ Username: email, Pool: userPool });
      cognitoUser.authenticateUser(
        new AuthenticationDetails({ Username: email, Password: password }),
        {
          onSuccess: (session) => {
            const payload = session.getIdToken().decodePayload();
            const tok = session.getIdToken().getJwtToken();
            setToken(tok);
            setUser({
              id: payload["custom:employee_id"],
              name: payload.name || payload.email,
              email: payload.email,
              role: payload["custom:role"] || "employee",
            });
            resolve();
          },
          onFailure: reject,
        }
      );
    });

  const logout = () => {
    userPool.getCurrentUser()?.signOut();
    setUser(null);
    setToken(null);
  };

  const api = async (path, options = {}) => {
    const res = await fetch(`${CONFIG.apiBase}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        Authorization: token ? `Bearer ${token}` : undefined,
        ...(options.headers || {}),
      },
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Request failed");
    return data;
  };

  return (
    <AuthCtx.Provider value={{ user, token, login, logout, api, loading }}>
      {children}
    </AuthCtx.Provider>
  );
}

// ─── Router (hash-based, no deps) ────────────────────────────────────────────
function useRoute() {
  const [route, setRoute] = useState(window.location.hash.slice(1) || "/");
  useEffect(() => {
    const handler = () => setRoute(window.location.hash.slice(1) || "/");
    window.addEventListener("hashchange", handler);
    return () => window.removeEventListener("hashchange", handler);
  }, []);
  const navigate = (path) => { window.location.hash = path; };
  return { route, navigate };
}

// ─── Design Tokens ────────────────────────────────────────────────────────────
const css = `
  @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,300&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg: #0f1117;
    --surface: #181c27;
    --surface2: #1e2336;
    --border: #2a3050;
    --accent: #6c8aff;
    --accent2: #a78bfa;
    --green: #34d399;
    --amber: #fbbf24;
    --red: #f87171;
    --text: #e8eaf4;
    --muted: #8892b0;
    --font-display: 'DM Serif Display', serif;
    --font-body: 'DM Sans', sans-serif;
    --radius: 12px;
    --radius-sm: 8px;
    --shadow: 0 4px 24px rgba(0,0,0,0.4);
  }

  body { background: var(--bg); color: var(--text); font-family: var(--font-body); font-size: 15px; line-height: 1.6; }

  .app { display: flex; min-height: 100vh; }

  /* Sidebar */
  .sidebar {
    width: 240px; background: var(--surface); border-right: 1px solid var(--border);
    display: flex; flex-direction: column; padding: 24px 16px; position: fixed;
    height: 100vh; top: 0; left: 0; z-index: 10;
  }
  .sidebar-logo { font-family: var(--font-display); font-size: 20px; color: var(--text); margin-bottom: 32px; padding: 0 8px; }
  .sidebar-logo span { color: var(--accent); }
  .nav-item {
    display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: var(--radius-sm);
    color: var(--muted); cursor: pointer; font-size: 14px; font-weight: 500;
    transition: all 0.15s; border: none; background: none; width: 100%; text-align: left;
  }
  .nav-item:hover { background: var(--surface2); color: var(--text); }
  .nav-item.active { background: rgba(108,138,255,0.12); color: var(--accent); }
  .nav-icon { width: 18px; height: 18px; flex-shrink: 0; }
  .sidebar-bottom { margin-top: auto; }
  .user-chip {
    background: var(--surface2); border-radius: var(--radius-sm); padding: 10px 12px;
    display: flex; align-items: center; gap: 10px;
  }
  .user-avatar {
    width: 32px; height: 32px; border-radius: 50%; background: linear-gradient(135deg, var(--accent), var(--accent2));
    display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 600; color: white;
  }
  .user-info { flex: 1; min-width: 0; }
  .user-name { font-size: 13px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .user-role { font-size: 11px; color: var(--muted); }
  .logout-btn { background: none; border: none; color: var(--muted); cursor: pointer; padding: 4px; border-radius: 4px; transition: color 0.15s; }
  .logout-btn:hover { color: var(--red); }

  /* Main content */
  .main { margin-left: 240px; flex: 1; padding: 40px; min-height: 100vh; }

  /* Page header */
  .page-header { margin-bottom: 32px; }
  .page-title { font-family: var(--font-display); font-size: 32px; color: var(--text); margin-bottom: 6px; }
  .page-subtitle { color: var(--muted); font-size: 14px; }

  /* Cards */
  .card {
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 24px; transition: border-color 0.2s;
  }
  .card:hover { border-color: var(--border); }
  .card-grid { display: grid; gap: 20px; }
  .card-grid-2 { grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); }
  .card-grid-4 { grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); }

  /* Stat boxes */
  .stat-box { text-align: center; }
  .stat-value { font-family: var(--font-display); font-size: 40px; line-height: 1; color: var(--text); }
  .stat-label { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; margin-top: 6px; }

  /* Badges */
  .badge {
    display: inline-flex; align-items: center; padding: 3px 10px; border-radius: 20px;
    font-size: 11px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase;
  }
  .badge-active { background: rgba(52,211,153,0.12); color: var(--green); border: 1px solid rgba(52,211,153,0.2); }
  .badge-closed { background: rgba(136,146,176,0.12); color: var(--muted); border: 1px solid var(--border); }
  .badge-hr { background: rgba(108,138,255,0.12); color: var(--accent); border: 1px solid rgba(108,138,255,0.2); }
  .badge-manager { background: rgba(167,139,250,0.12); color: var(--accent2); border: 1px solid rgba(167,139,250,0.2); }

  /* Buttons */
  .btn {
    display: inline-flex; align-items: center; gap: 8px; padding: 10px 20px;
    border-radius: var(--radius-sm); font-family: var(--font-body); font-size: 14px;
    font-weight: 500; cursor: pointer; border: none; transition: all 0.15s;
  }
  .btn-primary { background: var(--accent); color: white; }
  .btn-primary:hover { background: #5b79ff; }
  .btn-secondary { background: var(--surface2); color: var(--text); border: 1px solid var(--border); }
  .btn-secondary:hover { border-color: var(--accent); color: var(--accent); }
  .btn-danger { background: rgba(248,113,113,0.1); color: var(--red); border: 1px solid rgba(248,113,113,0.2); }
  .btn-sm { padding: 6px 14px; font-size: 13px; }

  /* Forms */
  .form-group { margin-bottom: 20px; }
  .label { display: block; font-size: 13px; font-weight: 500; color: var(--muted); margin-bottom: 8px; }
  .input {
    width: 100%; background: var(--surface2); border: 1px solid var(--border); border-radius: var(--radius-sm);
    padding: 10px 14px; color: var(--text); font-family: var(--font-body); font-size: 14px;
    transition: border-color 0.15s; outline: none;
  }
  .input:focus { border-color: var(--accent); }
  .textarea { resize: vertical; min-height: 80px; }
  select.input option { background: var(--surface2); }

  /* Rating stars */
  .rating-group { display: flex; gap: 8px; }
  .rating-btn {
    width: 40px; height: 40px; border-radius: var(--radius-sm); border: 1px solid var(--border);
    background: var(--surface2); color: var(--muted); font-size: 15px; font-weight: 600;
    cursor: pointer; transition: all 0.15s; display: flex; align-items: center; justify-content: center;
  }
  .rating-btn.selected { background: var(--accent); border-color: var(--accent); color: white; }
  .rating-btn:hover:not(.selected) { border-color: var(--accent); color: var(--accent); }

  /* Progress bar */
  .progress-track { background: var(--surface2); border-radius: 4px; height: 8px; overflow: hidden; }
  .progress-fill { height: 100%; border-radius: 4px; transition: width 0.5s ease; }

  /* Table */
  .table { width: 100%; border-collapse: collapse; }
  .table th { font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); padding: 10px 16px; text-align: left; border-bottom: 1px solid var(--border); }
  .table td { padding: 14px 16px; border-bottom: 1px solid rgba(42,48,80,0.5); font-size: 14px; }
  .table tr:last-child td { border-bottom: none; }
  .table tr:hover td { background: rgba(30,35,54,0.5); }

  /* Toast */
  .toast {
    position: fixed; bottom: 24px; right: 24px; padding: 12px 20px; border-radius: var(--radius-sm);
    font-size: 14px; font-weight: 500; z-index: 1000; animation: slideUp 0.2s ease;
    max-width: 360px; box-shadow: var(--shadow);
  }
  .toast-success { background: rgba(52,211,153,0.15); border: 1px solid rgba(52,211,153,0.3); color: var(--green); }
  .toast-error { background: rgba(248,113,113,0.15); border: 1px solid rgba(248,113,113,0.3); color: var(--red); }

  @keyframes slideUp { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

  /* Login page */
  .login-page {
    min-height: 100vh; display: flex; align-items: center; justify-content: center;
    background: radial-gradient(ellipse at 20% 50%, rgba(108,138,255,0.08) 0%, transparent 60%),
                radial-gradient(ellipse at 80% 20%, rgba(167,139,250,0.06) 0%, transparent 50%),
                var(--bg);
  }
  .login-card { width: 400px; }
  .login-title { font-family: var(--font-display); font-size: 36px; margin-bottom: 8px; }
  .login-subtitle { color: var(--muted); margin-bottom: 32px; font-size: 14px; }

  /* Loading spinner */
  .spinner { width: 20px; height: 20px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.6s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* Divider */
  .divider { height: 1px; background: var(--border); margin: 24px 0; }

  /* Section title */
  .section-title { font-family: var(--font-display); font-size: 20px; margin-bottom: 16px; }
  .section-subtitle { font-size: 13px; color: var(--muted); margin-top: 4px; margin-bottom: 20px; }

  /* Flag */
  .flag { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--red); background: rgba(248,113,113,0.08); border: 1px solid rgba(248,113,113,0.15); border-radius: 4px; padding: 2px 8px; }

  /* Empty state */
  .empty { text-align: center; padding: 60px 20px; color: var(--muted); }
  .empty-icon { font-size: 40px; margin-bottom: 12px; }
  .empty-text { font-size: 15px; }
`;

// ─── Toast ────────────────────────────────────────────────────────────────────
function Toast({ msg, type, onClose }) {
  useEffect(() => { const t = setTimeout(onClose, 3500); return () => clearTimeout(t); }, []);
  return <div className={`toast toast-${type}`}>{msg}</div>;
}

function useToast() {
  const [toasts, setToasts] = useState([]);
  const show = (msg, type = "success") => {
    const id = Date.now();
    setToasts(t => [...t, { id, msg, type }]);
  };
  const remove = (id) => setToasts(t => t.filter(x => x.id !== id));
  const Toasts = () => toasts.map(t => <Toast key={t.id} {...t} onClose={() => remove(t.id)} />);
  return { show, Toasts };
}

// ─── Login Page ───────────────────────────────────────────────────────────────
function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async () => {
    setLoading(true); setError("");
    try { await login(email, password); }
    catch (e) { setError(e.message || "Login failed"); }
    finally { setLoading(false); }
  };

  return (
    <div className="login-page">
      <div className="card login-card">
        <h1 className="login-title">360° Reviews</h1>
        <p className="login-subtitle">Performance management & OKR tracking</p>
        <div className="form-group">
          <label className="label">Email</label>
          <input className="input" type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@company.com" />
        </div>
        <div className="form-group">
          <label className="label">Password</label>
          <input className="input" type="password" value={password} onChange={e => setPassword(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleSubmit()} />
        </div>
        {error && <p style={{ color: "var(--red)", fontSize: 13, marginBottom: 16 }}>{error}</p>}
        <button className="btn btn-primary" style={{ width: "100%", justifyContent: "center" }} onClick={handleSubmit} disabled={loading}>
          {loading ? <span className="spinner" /> : "Sign In"}
        </button>
      </div>
    </div>
  );
}

// ─── Sidebar ──────────────────────────────────────────────────────────────────
function Sidebar({ route, navigate }) {
  const { user, logout } = useAuth();
  const role = user?.role;

  const navItems = [
    { path: "/", label: "Dashboard", icon: "⊞", roles: ["employee", "manager", "hr_admin"] },
    { path: "/cycles", label: "Review Cycles", icon: "⟳", roles: ["hr_admin", "manager"] },
    { path: "/review", label: "My Reviews", icon: "✎", roles: ["employee", "manager"] },
    { path: "/okr", label: "OKR Tracker", icon: "◎", roles: ["employee", "manager", "hr_admin"] },
    { path: "/reports", label: "Reports", icon: "▤", roles: ["hr_admin", "manager"] },
  ].filter(item => item.roles.includes(role));

  return (
    <div className="sidebar">
      <div className="sidebar-logo">360° <span>Reviews</span></div>
      <nav style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {navItems.map(item => (
          <button key={item.path} className={`nav-item ${route === item.path ? "active" : ""}`}
            onClick={() => navigate(item.path)}>
            <span className="nav-icon">{item.icon}</span>
            {item.label}
          </button>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <div className="user-chip">
          <div className="user-avatar">{user?.name?.[0]?.toUpperCase() || "?"}</div>
          <div className="user-info">
            <div className="user-name">{user?.name}</div>
            <div className="user-role">
              <span className={`badge badge-${role === "hr_admin" ? "hr" : role === "manager" ? "manager" : "active"}`}>
                {role}
              </span>
            </div>
          </div>
          <button className="logout-btn" onClick={logout} title="Sign out">✕</button>
        </div>
      </div>
    </div>
  );
}

// ─── Dashboard Page ───────────────────────────────────────────────────────────
function DashboardPage({ navigate }) {
  const { user, api } = useAuth();
  const [cycles, setCycles] = useState([]);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api("/cycles"),
      user.role === "employee" ? api(`/review/status/${user.id}`) : Promise.resolve(null),
    ]).then(([cyclesData, statusData]) => {
      setCycles(cyclesData.cycles || []);
      if (statusData) setStatus(statusData.status || []);
    }).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="empty"><div className="spinner" style={{ margin: "0 auto" }} /></div>;

  const activeCycles = cycles.filter(c => c.status === "active");

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Welcome back, {user.name?.split(" ")[0]}</h1>
        <p className="page-subtitle">{new Date().toLocaleDateString("en-US", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}</p>
      </div>

      <div className="card-grid card-grid-4" style={{ marginBottom: 24 }}>
        <div className="card stat-box">
          <div className="stat-value">{activeCycles.length}</div>
          <div className="stat-label">Active Cycles</div>
        </div>
        <div className="card stat-box">
          <div className="stat-value" style={{ color: "var(--amber)" }}>
            {status?.reduce((n, c) => n + c.pending_reviews.length, 0) ?? "—"}
          </div>
          <div className="stat-label">Pending Reviews</div>
        </div>
        <div className="card stat-box">
          <div className="stat-value" style={{ color: "var(--green)" }}>
            {status?.reduce((n, c) => n + c.peer_reviews_given, 0) ?? "—"}
          </div>
          <div className="stat-label">Peer Reviews Given</div>
        </div>
        <div className="card stat-box">
          <div className="stat-value">{cycles.filter(c => c.status === "closed").length}</div>
          <div className="stat-label">Completed Cycles</div>
        </div>
      </div>

      {status && status.length > 0 && (
        <div className="card" style={{ marginBottom: 24 }}>
          <h3 className="section-title">Your pending actions</h3>
          <table className="table">
            <thead><tr><th>Cycle</th><th>Deadline</th><th>Pending</th><th></th></tr></thead>
            <tbody>
              {status.map(s => (
                <tr key={s.cycle_id}>
                  <td style={{ fontWeight: 500 }}>{s.cycle_name}</td>
                  <td style={{ color: "var(--muted)" }}>{s.end_date}</td>
                  <td>
                    {s.pending_reviews.map(r => (
                      <span key={r} className="badge badge-active" style={{ marginRight: 6 }}>{r}</span>
                    ))}
                  </td>
                  <td><button className="btn btn-sm btn-primary" onClick={() => navigate("/review")}>Submit</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="card">
        <h3 className="section-title">Recent cycles</h3>
        {cycles.length === 0 ? (
          <div className="empty"><div className="empty-icon">◎</div><div className="empty-text">No review cycles yet</div></div>
        ) : (
          <table className="table">
            <thead><tr><th>Name</th><th>Start</th><th>End</th><th>Status</th><th>Employees</th></tr></thead>
            <tbody>
              {cycles.slice(0, 5).map(c => (
                <tr key={c.cycle_id}>
                  <td style={{ fontWeight: 500 }}>{c.name}</td>
                  <td style={{ color: "var(--muted)" }}>{c.start_date}</td>
                  <td style={{ color: "var(--muted)" }}>{c.end_date}</td>
                  <td><span className={`badge badge-${c.status}`}>{c.status}</span></td>
                  <td>{c.employee_ids?.length ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ─── Cycles Page (HR Admin) ───────────────────────────────────────────────────
function CyclesPage() {
  const { api } = useAuth();
  const { show, Toasts } = useToast();
  const [cycles, setCycles] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [creating, setCreating] = useState(false);
  const [selectedEmployees, setSelectedEmployees] = useState([]);
  const [form, setForm] = useState({ name: "", start_date: "", end_date: "" });

  useEffect(() => {
    api("/cycles").then(d => setCycles(d.cycles || []));
    api("/employees").then(d => setEmployees(d.employees || []));
  }, []);

  const toggleEmployee = (empId) => {
    setSelectedEmployees(prev =>
      prev.includes(empId) ? prev.filter(id => id !== empId) : [...prev, empId]
    );
  };

  const selectAll = () => setSelectedEmployees(employees.map(e => e.employee_id));
  const clearAll = () => setSelectedEmployees([]);

  const createCycle = async () => {
    if (selectedEmployees.length === 0) {
      show("Please select at least one employee", "error");
      return;
    }
    try {
      await api("/cycles", {
        method: "POST",
        body: JSON.stringify({ ...form, employee_ids: selectedEmployees }),
      });
      show("Review cycle created and notifications sent!");
      setCreating(false);
      setForm({ name: "", start_date: "", end_date: "" });
      setSelectedEmployees([]);
      api("/cycles").then(d => setCycles(d.cycles || []));
    } catch (e) { show(e.message, "error"); }
  };

  const deleteCycle = async (cycleId, cycleName) => {
    if (!window.confirm(`Delete cycle "${cycleName}"?\n\nThis will permanently delete:\n• The review cycle\n• All generated S3 reports\n\nThis cannot be undone.`)) return;
    try {
      // 1. Delete S3 reports first
      try {
        await api(`/report/${cycleId}`, { method: "DELETE" });
      } catch (e) {
        // Non-fatal — reports may not exist yet
        console.log("S3 cleanup:", e.message);
      }
      // 2. Delete the cycle from DynamoDB
      await api(`/cycles/${cycleId}`, { method: "DELETE" });
      show(`Cycle "${cycleName}" and all reports deleted.`);
      api("/cycles").then(d => setCycles(d.cycles || []));
    } catch (e) {
      show(e.message || "Failed to delete cycle", "error");
    }
  };

  return (
    <div>
      <Toasts />
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h1 className="page-title">Review Cycles</h1>
          <p className="page-subtitle">Create and manage performance review cycles</p>
        </div>
        <button className="btn btn-primary" onClick={() => setCreating(true)}>+ New Cycle</button>
      </div>

      {creating && (
        <div className="card" style={{ marginBottom: 24 }}>
          <h3 className="section-title">Create Review Cycle</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <div className="form-group" style={{ gridColumn: "1/-1" }}>
              <label className="label">Cycle Name</label>
              <input className="input" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="Q4 2025 Performance Review" />
            </div>
            <div className="form-group">
              <label className="label">Start Date</label>
              <input className="input" type="date" value={form.start_date} onChange={e => setForm(f => ({ ...f, start_date: e.target.value }))} />
            </div>
            <div className="form-group">
              <label className="label">End Date</label>
              <input className="input" type="date" value={form.end_date} onChange={e => setForm(f => ({ ...f, end_date: e.target.value }))} />
            </div>
            <div className="form-group" style={{ gridColumn: "1/-1" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <label className="label" style={{ marginBottom: 0 }}>
                  Select Employees ({selectedEmployees.length} selected)
                </label>
                <div style={{ display: "flex", gap: 8 }}>
                  <button type="button" className="btn btn-sm btn-secondary" onClick={selectAll}>Select All</button>
                  <button type="button" className="btn btn-sm btn-secondary" onClick={clearAll}>Clear</button>
                </div>
              </div>
              <div style={{
                border: "1px solid var(--border)", borderRadius: "var(--radius-sm)",
                background: "var(--surface2)", padding: 8, maxHeight: 200, overflowY: "auto"
              }}>
                {employees.length === 0 ? (
                  <div style={{ color: "var(--muted)", padding: 8, fontSize: 13 }}>Loading employees...</div>
                ) : (
                  employees.map(emp => (
                    <label key={emp.employee_id} onClick={() => toggleEmployee(emp.employee_id)}
                      style={{
                        display: "flex", alignItems: "center", gap: 12, padding: "8px 10px",
                        cursor: "pointer", borderRadius: 6, marginBottom: 2,
                        background: selectedEmployees.includes(emp.employee_id) ? "rgba(79,110,255,0.1)" : "transparent",
                        border: selectedEmployees.includes(emp.employee_id) ? "1px solid rgba(79,110,255,0.3)" : "1px solid transparent",
                        transition: "all 0.15s"
                      }}>
                      <div style={{
                        width: 18, height: 18, borderRadius: 4, flexShrink: 0,
                        border: selectedEmployees.includes(emp.employee_id) ? "2px solid var(--accent)" : "2px solid var(--border)",
                        background: selectedEmployees.includes(emp.employee_id) ? "var(--accent)" : "transparent",
                        display: "flex", alignItems: "center", justifyContent: "center"
                      }}>
                        {selectedEmployees.includes(emp.employee_id) && (
                          <span style={{ color: "white", fontSize: 11, fontWeight: 700 }}>✓</span>
                        )}
                      </div>
                      <div>
                        <div style={{ fontWeight: 500, fontSize: 13 }}>{emp.name}</div>
                        <div style={{ fontSize: 11, color: "var(--muted)" }}>{emp.employee_id} · {emp.role} · {emp.department}</div>
                      </div>
                    </label>
                  ))
                )}
              </div>
            </div>
          </div>
          <div style={{ display: "flex", gap: 12 }}>
            <button className="btn btn-primary" onClick={createCycle}>Create Cycle</button>
            <button className="btn btn-secondary" onClick={() => setCreating(false)}>Cancel</button>
          </div>
        </div>
      )}

      <div className="card">
        {cycles.length === 0 ? (
          <div className="empty"><div className="empty-icon">⟳</div><div className="empty-text">No review cycles created yet</div></div>
        ) : (
          <table className="table">
            <thead><tr><th>Name</th><th>Start</th><th>End</th><th>Status</th><th>Employees</th><th>Self Reviews</th><th></th></tr></thead>
            <tbody>
              {cycles.map(c => {
                const stats = c.submission_stats || {};
                const total = stats.total_employees || 0;
                const self = stats.self_reviews_submitted || 0;
                const pct = total ? Math.round(self / total * 100) : 0;
                return (
                  <tr key={c.cycle_id}>
                    <td>
                      <div style={{ fontWeight: 500 }}>{c.name}</div>
                      <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4 }}>
                        <span style={{ fontSize: 11, color: "var(--muted)", fontFamily: "monospace", background: "var(--surface)", padding: "2px 6px", borderRadius: 4, letterSpacing: "0.02em" }}>
                          {c.cycle_id}
                        </span>
                        <button
                          onClick={(e) => {
                            navigator.clipboard.writeText(c.cycle_id);
                            const btn = e.target;
                            const prev = btn.innerText;
                            btn.innerText = "✓ Copied!";
                            btn.style.color = "var(--green)";
                            setTimeout(() => { btn.innerText = prev; btn.style.color = "var(--muted)"; }, 1500);
                          }}
                          title="Copy cycle ID"
                          style={{ background: "none", border: "none", cursor: "pointer", color: "var(--muted)", fontSize: 12, padding: "2px 4px", borderRadius: 4, lineHeight: 1, transition: "color 0.2s" }}
                          onMouseEnter={e => { if(e.target.innerText !== "✓ Copied!") e.target.style.color = "var(--accent)"; }}
                          onMouseLeave={e => { if(e.target.innerText !== "✓ Copied!") e.target.style.color = "var(--muted)"; }}
                        >
                          ⎘ copy
                        </button>
                      </div>
                    </td>
                    <td style={{ color: "var(--muted)" }}>{c.start_date}</td>
                    <td style={{ color: "var(--muted)" }}>{c.end_date}</td>
                    <td><span className={`badge badge-${c.status}`}>{c.status}</span></td>
                    <td>{total}</td>
                    <td>
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <div className="progress-track" style={{ width: 80 }}>
                          <div className="progress-fill" style={{ width: `${pct}%`, background: pct >= 80 ? "var(--green)" : pct >= 50 ? "var(--amber)" : "var(--red)" }} />
                        </div>
                        <span style={{ fontSize: 12, color: "var(--muted)" }}>{self}/{total}</span>
                      </div>
                    </td>
                    <td>
                      <button
                        onClick={() => deleteCycle(c.cycle_id, c.name)}
                        title="Delete cycle"
                        style={{ background: "none", border: "1px solid var(--red)", cursor: "pointer", color: "var(--red)", fontSize: 12, padding: "4px 10px", borderRadius: 6, fontWeight: 500, transition: "all 0.15s" }}
                        onMouseEnter={e => { e.target.style.background = "var(--red)"; e.target.style.color = "#fff"; }}
                        onMouseLeave={e => { e.target.style.background = "none"; e.target.style.color = "var(--red)"; }}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ─── Review Form Page ─────────────────────────────────────────────────────────
function ReviewPage() {
  const { user, api } = useAuth();
  const { show, Toasts } = useToast();
  const [status, setStatus] = useState(null);
  const [cycles, setCycles] = useState([]);
  const [selectedCycle, setSelectedCycle] = useState("");
  const [cycleEmployees, setCycleEmployees] = useState([]);
  const [formType, setFormType] = useState("self");
  const [revieweeId, setRevieweeId] = useState("");
  const [form, setForm] = useState(null);
  const [answers, setAnswers] = useState({});
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (user.id) {
      api(`/review/status/${user.id}`).then(d => setStatus(d.status || []));
    }
    api("/cycles").then(d => setCycles(d.cycles || []));
  }, []);

  // When cycle changes, populate employee list from that cycle
  const handleCycleChange = (cycleId) => {
    setSelectedCycle(cycleId);
    setRevieweeId("");
    const found = cycles.find(c => c.cycle_id === cycleId);
    setCycleEmployees(found ? (found.employee_ids || []) : []);
  };

  const loadForm = async () => {
    const f = await api(`/forms/${formType}`);
    setForm(f.form);
    setAnswers({});
  };

  const submit = async () => {
    setSubmitting(true);
    try {
      const responses = Object.entries(answers).map(([question_id, value]) => ({ question_id, value }));
      await api("/review/submit", {
        method: "POST",
        body: JSON.stringify({
          cycle_id: selectedCycle,
          reviewee_id: formType === "self" ? user.id : revieweeId,
          review_type: formType,
          responses,
        }),
      });
      show("Review submitted successfully!");
      setForm(null);
      setAnswers({});
      if (user.id) {
        api(`/review/status/${user.id}`).then(d => setStatus(d.status || []));
      }
    } catch (e) { show(e.message, "error"); }
    finally { setSubmitting(false); }
  };

  return (
    <div>
      <Toasts />
      <div className="page-header">
        <h1 className="page-title">My Reviews</h1>
        <p className="page-subtitle">Submit performance reviews</p>
      </div>

      {status && status.length > 0 && (
        <div className="card" style={{ marginBottom: 24 }}>
          <h3 className="section-title">Pending Reviews</h3>
          <div className="card-grid card-grid-2">
            {status.flatMap(s =>
              s.pending_reviews.map(r => (
                <div key={s.cycle_id + r} style={{ background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: 16, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <div style={{ fontWeight: 500 }}>{s.cycle_name}</div>
                    <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>Due {s.end_date}</div>
                  </div>
                  <button className="btn btn-sm btn-primary" onClick={() => { setSelectedCycle(s.cycle_id); setFormType(r); }}>
                    {r} review
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      <div className="card">
        <h3 className="section-title">Submit a Review</h3>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr auto", gap: 12, marginBottom: 20, alignItems: "flex-end" }}>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="label">Select Cycle</label>
            <select className="input" value={selectedCycle} onChange={e => handleCycleChange(e.target.value)}>
              <option value="">— choose a cycle —</option>
              {cycles.map(c => (
                <option key={c.cycle_id} value={c.cycle_id}>
                  {c.name} ({c.status})
                </option>
              ))}
            </select>
          </div>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label className="label">Review Type</label>
            <select className="input" value={formType} onChange={e => { setFormType(e.target.value); setRevieweeId(""); }}>
              <option value="self">Self Review</option>
              {user.role !== "employee" && <option value="manager">Manager Review</option>}
              <option value="peer">Peer Review (Anonymous)</option>
            </select>
          </div>
          {formType !== "self" && (
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="label">Reviewee</label>
              {cycleEmployees.length > 0 ? (
                <select className="input" value={revieweeId} onChange={e => setRevieweeId(e.target.value)}>
                  <option value="">— select employee —</option>
                  {cycleEmployees
                    .filter(id => id !== user.id)
                    .map(id => (
                      <option key={id} value={id}>{id}</option>
                    ))}
                </select>
              ) : (
                <input className="input" value={revieweeId} onChange={e => setRevieweeId(e.target.value)} placeholder="emp-001" />
              )}
            </div>
          )}
          <button className="btn btn-secondary" onClick={loadForm} disabled={!selectedCycle}>Load Form</button>
        </div>

        {formType === "peer" && (
          <div style={{ background: "rgba(108,138,255,0.06)", border: "1px solid rgba(108,138,255,0.15)", borderRadius: "var(--radius-sm)", padding: "12px 16px", marginBottom: 20, fontSize: 13, color: "var(--muted)" }}>
            🔒 Peer reviews are anonymous. Your identity is protected by one-way cryptographic hashing and will never be disclosed to the reviewee.
          </div>
        )}

        {form && (
          <div>
            <div className="divider" />
            <h4 style={{ marginBottom: 20, color: "var(--text)" }}>{form.title}</h4>
            {form.questions.map((q, i) => (
              <div key={q.id} className="form-group">
                <label className="label">{i + 1}. {q.text}</label>
                {q.type === "rating" ? (
                  <div className="rating-group">
                    {[1, 2, 3, 4, 5].map(n => (
                      <button key={n} className={`rating-btn ${answers[q.id] === n ? "selected" : ""}`}
                        onClick={() => setAnswers(a => ({ ...a, [q.id]: n }))}>
                        {n}
                      </button>
                    ))}
                    <span style={{ alignSelf: "center", fontSize: 12, color: "var(--muted)", marginLeft: 8 }}>
                      {["", "Poor", "Below average", "Average", "Good", "Excellent"][answers[q.id]] || ""}
                    </span>
                  </div>
                ) : (
                  <textarea className="input textarea" value={answers[q.id] || ""} onChange={e => setAnswers(a => ({ ...a, [q.id]: e.target.value }))} rows={3} />
                )}
              </div>
            ))}
            <button className="btn btn-primary" onClick={submit} disabled={submitting}>
              {submitting ? <span className="spinner" /> : "Submit Review"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── OKR Page ─────────────────────────────────────────────────────────────────
function OKRPage() {
  const { user, api } = useAuth();
  const { show, Toasts } = useToast();
  const [okrs, setOkrs] = useState([]);
  const [creating, setCreating] = useState(false);
  const [updating, setUpdating] = useState(null);
  const [krProgress, setKrProgress] = useState({});
  const [form, setForm] = useState({ objective_title: "", quarter: "", key_results: [{ title: "", target_metric: "" }] });
  const [allEmployees, setAllEmployees] = useState([]);
  const [viewingEmployee, setViewingEmployee] = useState(user.id || "");

  const quarter = (() => { const n = new Date(); return `${n.getFullYear()}-Q${Math.floor(n.getMonth()/3)+1}`; })();

  const loadOkrs = (empId) => {
    if (!empId) return;
    api(`/okr/employee/${empId}?quarter=${quarter}`).then(d => setOkrs(d.okrs || []));
  };

  useEffect(() => {
    // For manager/HR: get unique employee IDs from all cycles
    if (user.role !== "employee") {
      api("/cycles").then(d => {
        const allCycles = d.cycles || [];
        const ids = [...new Set(allCycles.flatMap(c => c.employee_ids || []))];
        setAllEmployees(ids);
        // Auto-select first employee and load their OKRs if manager has no own employee_id
        if (!user.id && ids.length > 0) {
          setViewingEmployee(ids[0]);
          loadOkrs(ids[0]);
        }
      });
    }
    if (user.id) {
      setViewingEmployee(user.id);
      loadOkrs(user.id);
    }
  }, []);

  const addKR = () => setForm(f => ({ ...f, key_results: [...f.key_results, { title: "", target_metric: "" }].slice(0, 3) }));

  const createOKR = async () => {
    try {
      await api("/okr", { method: "POST", body: JSON.stringify({ ...form, quarter }) });
      show("OKR created!");
      setCreating(false);
      loadOkrs(viewingEmployee || user.id);
    } catch (e) { show(e.message, "error"); }
  };

  const updateProgress = async (okr_id) => {
    try {
      const kr_updates = Object.entries(krProgress).map(([kr_id, progress]) => ({ kr_id, progress: parseInt(progress) }));
      await api(`/okr/${okr_id}`, { method: "PUT", body: JSON.stringify({ kr_updates }) });
      show("Progress updated!");
      setUpdating(null);
      setKrProgress({});
      loadOkrs(viewingEmployee || user.id);
    } catch (e) { show(e.message, "error"); }
  };

  const progressColor = (pct) => pct >= 70 ? "var(--green)" : pct >= 40 ? "var(--amber)" : "var(--red)";

  return (
    <div>
      <Toasts />
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h1 className="page-title">OKR Tracker</h1>
          <p className="page-subtitle">{quarter} — Objectives & Key Results</p>
        </div>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          {user.role !== "employee" && allEmployees.length > 0 && (
            <div className="form-group" style={{ marginBottom: 0 }}>
              <select className="input" value={viewingEmployee}
                onChange={e => { setViewingEmployee(e.target.value); loadOkrs(e.target.value); }}
                style={{ minWidth: 160 }}>
                <option value="">— select employee —</option>
                {allEmployees.map(id => <option key={id} value={id}>{id}</option>)}
              </select>
            </div>
          )}
          {(user.role === "employee" || viewingEmployee === user.id) && (
            <button className="btn btn-primary" onClick={() => setCreating(true)}>+ New Objective</button>
          )}
        </div>
      </div>

      {creating && (
        <div className="card" style={{ marginBottom: 24 }}>
          <h3 className="section-title">New Objective</h3>
          <div className="form-group">
            <label className="label">Objective Title</label>
            <input className="input" value={form.objective_title} onChange={e => setForm(f => ({ ...f, objective_title: e.target.value }))} placeholder="e.g., Launch new product feature" />
          </div>
          <h4 style={{ color: "var(--muted)", fontSize: 13, marginBottom: 12, fontWeight: 500 }}>KEY RESULTS (max 3)</h4>
          {form.key_results.map((kr, i) => (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label className="label">KR {i+1} Title</label>
                <input className="input" value={kr.title} onChange={e => { const krs = [...form.key_results]; krs[i].title = e.target.value; setForm(f => ({ ...f, key_results: krs })); }} placeholder="Key result description" />
              </div>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label className="label">Target Metric</label>
                <input className="input" value={kr.target_metric} onChange={e => { const krs = [...form.key_results]; krs[i].target_metric = e.target.value; setForm(f => ({ ...f, key_results: krs })); }} placeholder="e.g., 100% done, 99.9% uptime" />
              </div>
            </div>
          ))}
          {form.key_results.length < 3 && (
            <button className="btn btn-secondary btn-sm" style={{ marginBottom: 16 }} onClick={addKR}>+ Add Key Result</button>
          )}
          <div style={{ display: "flex", gap: 12 }}>
            <button className="btn btn-primary" onClick={createOKR}>Create OKR</button>
            <button className="btn btn-secondary" onClick={() => setCreating(false)}>Cancel</button>
          </div>
        </div>
      )}

      {okrs.length === 0 && !creating ? (
        <div className="card empty">
          <div className="empty-icon">◎</div>
          <div className="empty-text">No OKRs for {quarter} yet. Create your first objective.</div>
        </div>
      ) : (
        <div className="card-grid" style={{ gridTemplateColumns: "1fr" }}>
          {okrs.map(okr => (
            <div key={okr.okr_id} className="card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
                <div>
                  <h3 style={{ fontSize: 18, fontWeight: 600 }}>{okr.objective_title}</h3>
                  <span className="badge badge-active" style={{ marginTop: 6 }}>{okr.quarter}</span>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: 28, fontFamily: "var(--font-display)", color: progressColor(okr.overall_completion) }}>
                    {okr.overall_completion}%
                  </div>
                  <div style={{ fontSize: 11, color: "var(--muted)" }}>overall</div>
                </div>
              </div>
              <div className="progress-track" style={{ marginBottom: 20 }}>
                <div className="progress-fill" style={{ width: `${okr.overall_completion}%`, background: progressColor(okr.overall_completion) }} />
              </div>
              {okr.key_results.map(kr => (
                <div key={kr.kr_id} style={{ marginBottom: 16 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                    <span style={{ fontSize: 14, fontWeight: 500 }}>{kr.title}</span>
                    <span style={{ fontSize: 13, color: "var(--muted)" }}>{kr.progress}%</span>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 6 }}>Target: {kr.target_metric}</div>
                  {updating === okr.okr_id ? (
                    <input type="range" min="0" max="100" value={krProgress[kr.kr_id] ?? kr.progress}
                      onChange={e => setKrProgress(p => ({ ...p, [kr.kr_id]: e.target.value }))}
                      style={{ width: "100%", accentColor: "var(--accent)" }} />
                  ) : (
                    <div className="progress-track">
                      <div className="progress-fill" style={{ width: `${kr.progress}%`, background: progressColor(kr.progress) }} />
                    </div>
                  )}
                </div>
              ))}
              <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
                {updating === okr.okr_id ? (
                  <>
                    <button className="btn btn-sm btn-primary" onClick={() => updateProgress(okr.okr_id)}>Save Progress</button>
                    <button className="btn btn-sm btn-secondary" onClick={() => { setUpdating(null); setKrProgress({}); }}>Cancel</button>
                  </>
                ) : (
                  <button className="btn btn-sm btn-secondary" onClick={() => { setUpdating(okr.okr_id); setKrProgress({}); }}>Update Progress</button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Reports Page (HR / Manager) ─────────────────────────────────────────────
function ReportsPage() {
  const { user, api } = useAuth();
  const { show, Toasts } = useToast();
  const [cycleId, setCycleId] = useState("");
  const [cycles, setCycles] = useState([]);
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(false);
  // Manager-specific state
  const [mgr_employeeId, setMgrEmployeeId] = useState("");
  const [mgr_cycleEmployees, setMgrCycleEmployees] = useState([]);
  const [mgr_generating, setMgrGenerating] = useState(false);

  useEffect(() => {
    api("/cycles").then(d => setCycles(d.cycles || []));
  }, []);

  const handleCycleSelect = (id) => {
    setCycleId(id);
    setDashboard(null);
    setMgrEmployeeId("");
    const found = cycles.find(c => c.cycle_id === id);
    setMgrCycleEmployees(found ? (found.employee_ids || []) : []);
  };

  const loadDashboard = async () => {
    setLoading(true);
    try {
      const d = await api(`/dashboard/${cycleId}`);
      setDashboard(d);
    } catch (e) { show(e.message, "error"); }
    finally { setLoading(false); }
  };

  const viewReport = async (employeeId) => {
    try {
      const d = await api(`/report/${cycleId}/${employeeId}`);
      window.open(d.report_url, "_blank");
    } catch (e) { show("Report not yet generated — generate it first", "error"); }
  };

  const generateReport = async (employeeId) => {
    try {
      await api(`/report/${cycleId}/${employeeId}`, { method: "POST" });
      show("Report generated successfully!");
    } catch (e) { show(e.message, "error"); }
  };

  const downloadReport = async (employeeId, employeeName) => {
    try {
      const d = await api(`/report/${cycleId}/${employeeId}`);
      // Fetch the HTML content and trigger download
      const response = await fetch(d.report_url);
      const html = await response.text();
      const blob = new Blob([html], { type: "text/html" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `performance-report-${employeeName || employeeId}.html`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) { show("Report not yet generated — generate it first", "error"); }
  };

  const mgrGenerateAndView = async () => {
    if (!cycleId || !mgr_employeeId) return;
    setMgrGenerating(true);
    try {
      await api(`/report/${cycleId}/${mgr_employeeId}`, { method: "POST" });
      show("Report generated!");
      const d = await api(`/report/${cycleId}/${mgr_employeeId}`);
      window.open(d.report_url, "_blank");
    } catch (e) { show(e.message, "error"); }
    finally { setMgrGenerating(false); }
  };

  const ratingColor = (r) => !r ? "var(--muted)" : r >= 4 ? "var(--green)" : r >= 3 ? "var(--amber)" : "var(--red)";

  // ── Manager view ──────────────────────────────────────────────────────────
  if (user.role === "manager") {
    return (
      <div>
        <Toasts />
        <div className="page-header">
          <h1 className="page-title">Generate Reports</h1>
          <p className="page-subtitle">Generate and view performance reports for your employees</p>
        </div>
        <div className="card">
          <h3 className="section-title">Select Cycle & Employee</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 20 }}>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="label">Review Cycle</label>
              <select className="input" value={cycleId} onChange={e => handleCycleSelect(e.target.value)}>
                <option value="">— choose a cycle —</option>
                {cycles.map(c => (
                  <option key={c.cycle_id} value={c.cycle_id}>
                    {c.name} ({c.status}) — {c.start_date} to {c.end_date}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="label">Employee</label>
              <select className="input" value={mgr_employeeId} onChange={e => setMgrEmployeeId(e.target.value)} disabled={!cycleId}>
                <option value="">— select employee —</option>
                {mgr_cycleEmployees.map(id => (
                  <option key={id} value={id}>{id}</option>
                ))}
              </select>
            </div>
          </div>
          <div style={{ display: "flex", gap: 12 }}>
            <button className="btn btn-primary" onClick={mgrGenerateAndView}
              disabled={!cycleId || !mgr_employeeId || mgr_generating}>
              {mgr_generating ? <span className="spinner" /> : "Generate & View Report"}
            </button>
            <button className="btn btn-secondary" onClick={() => viewReport(mgr_employeeId)}
              disabled={!cycleId || !mgr_employeeId}>
              View Report
            </button>
            <button className="btn btn-secondary" onClick={() => downloadReport(mgr_employeeId, mgr_employeeId)}
              disabled={!cycleId || !mgr_employeeId}
              style={{ display: "flex", alignItems: "center", gap: 6 }}>
              ⬇ Download Report
            </button>
          </div>
          <p style={{ fontSize: 12, color: "var(--muted)", marginTop: 16 }}>
            Generate Report creates a fresh HTML report with composite scores, peer feedback, and OKR progress. 
            View Existing Report opens the last generated version.
          </p>
        </div>
      </div>
    );
  }

  // ── HR Admin view ─────────────────────────────────────────────────────────
  return (
    <div>
      <Toasts />
      <div className="page-header">
        <h1 className="page-title">Reports & Dashboard</h1>
        <p className="page-subtitle">View cycle completion and employee performance reports</p>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <h3 className="section-title">Load Cycle Dashboard</h3>
        <div style={{ display: "flex", gap: 12, alignItems: "flex-end" }}>
          <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
            <label className="label">Select Cycle</label>
            <select className="input" value={cycleId} onChange={e => handleCycleSelect(e.target.value)}>
              <option value="">— choose a cycle —</option>
              {cycles.map(c => (
                <option key={c.cycle_id} value={c.cycle_id}>
                  {c.name} ({c.status}) — {c.start_date} to {c.end_date}
                </option>
              ))}
            </select>
          </div>
          <button className="btn btn-primary" onClick={loadDashboard} disabled={!cycleId || loading}>
            {loading ? <span className="spinner" /> : "Load"}
          </button>
        </div>
      </div>

      {dashboard && (
        <>
          <div className="card-grid card-grid-4" style={{ marginBottom: 24 }}>
            <div className="card stat-box">
              <div className="stat-value">{dashboard.total_employees}</div>
              <div className="stat-label">Total Employees</div>
            </div>
            <div className="card stat-box">
              <div className="stat-value" style={{ color: dashboard.completion_rate >= 80 ? "var(--green)" : "var(--amber)" }}>
                {dashboard.completion_rate}%
              </div>
              <div className="stat-label">Completion Rate</div>
            </div>
            <div className="card stat-box">
              <div className="stat-value" style={{ color: ratingColor(dashboard.average_ratings.manager) }}>
                {dashboard.average_ratings.manager ?? "—"}
              </div>
              <div className="stat-label">Avg Manager Rating</div>
            </div>
            <div className="card stat-box">
              <div className="stat-value" style={{ color: ratingColor(dashboard.average_ratings.peer) }}>
                {dashboard.average_ratings.peer ?? "—"}
              </div>
              <div className="stat-label">Avg Peer Rating</div>
            </div>
          </div>

          {dashboard.ratings_by_team && Object.keys(dashboard.ratings_by_team).length > 0 && (
            <div className="card" style={{ marginBottom: 24 }}>
              <h3 className="section-title">Average Ratings by Team</h3>
              <table className="table">
                <thead><tr><th>Department</th><th>Avg Rating</th><th>Performance</th></tr></thead>
                <tbody>
                  {Object.entries(dashboard.ratings_by_team).sort((a,b) => b[1]-a[1]).map(([dept, rating]) => (
                    <tr key={dept}>
                      <td style={{ fontWeight: 500 }}>{dept}</td>
                      <td style={{ color: ratingColor(rating), fontWeight: 600 }}>{rating} / 5.0</td>
                      <td>
                        <div className="progress-track" style={{ width: 120 }}>
                          <div className="progress-fill" style={{ width: `${(rating/5)*100}%`, background: ratingColor(rating) }} />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {dashboard.no_reviews_submitted?.length > 0 && (
            <div className="card" style={{ marginBottom: 24, borderColor: "rgba(248,113,113,0.2)" }}>
              <h3 style={{ color: "var(--red)", marginBottom: 12 }}>⚠ No reviews submitted</h3>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {dashboard.no_reviews_submitted.map(id => (
                  <span key={id} className="flag">{id}</span>
                ))}
              </div>
            </div>
          )}

          <div className="card">
            <h3 className="section-title">{dashboard.cycle_name} — Employee Status</h3>
            <table className="table">
              <thead>
                <tr><th>Employee</th><th>Department</th><th>Self</th><th>Manager</th><th>Peers</th><th>Composite</th><th>Actions</th></tr>
              </thead>
              <tbody>
                {dashboard.employee_status.map(emp => (
                  <tr key={emp.employee_id}>
                    <td>
                      <div style={{ fontWeight: 500 }}>{emp.name || emp.employee_id}</div>
                      <div style={{ fontSize: 12, color: "var(--muted)" }}>{emp.role}</div>
                    </td>
                    <td style={{ color: "var(--muted)" }}>{emp.department}</td>
                    <td>{emp.self_submitted ? <span style={{color:"var(--green)"}}>✓</span> : <span style={{ color: "var(--red)" }}>✗</span>}</td>
                    <td>{emp.manager_submitted ? <span style={{color:"var(--green)"}}>✓</span> : <span style={{ color: "var(--amber)" }}>—</span>}</td>
                    <td>{emp.peer_count}</td>
                    <td style={{ fontWeight: 600, color: ratingColor(emp.composite_rating) }}>
                      {emp.composite_rating ? `${emp.composite_rating}/5` : <span style={{color:"var(--muted)"}}>—</span>}
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: 6 }}>
                        <button className="btn btn-sm btn-secondary" onClick={() => generateReport(emp.employee_id)}>Generate</button>
                        <button className="btn btn-sm btn-primary" onClick={() => viewReport(emp.employee_id)}>View</button>
                        <button className="btn btn-sm btn-secondary" onClick={() => downloadReport(emp.employee_id, emp.name || emp.employee_id)}
                          style={{ display: "flex", alignItems: "center", gap: 4 }}>
                          ⬇ Download
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

// ─── Root App ─────────────────────────────────────────────────────────────────
export default function App() {
  const { user, loading } = useAuth();
  const { route, navigate } = useRoute();

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh" }}>
      <div className="spinner" style={{ width: 32, height: 32 }} />
    </div>
  );

  if (!user) return <LoginPage />;

  const pages = {
    "/": <DashboardPage navigate={navigate} />,
    "/cycles": <CyclesPage />,
    "/review": <ReviewPage />,
    "/okr": <OKRPage />,
    "/reports": <ReportsPage />,
  };

  return (
    <div className="app">
      <style>{css}</style>
      <Sidebar route={route} navigate={navigate} />
      <main className="main">{pages[route] || pages["/"]}</main>
    </div>
  );
}

// Wrap in provider at entry point (main.jsx):
// import { AuthProvider } from './App'
// ReactDOM.createRoot(...).render(<AuthProvider><App /></AuthProvider>)
