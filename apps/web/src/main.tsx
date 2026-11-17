import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { fetchHealth } from './health';
import './style.css';

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1 } } });
function Status({ title, kind }: { title: string; kind: 'live' | 'ready' }) {
  const query = useQuery({ queryKey: ['health', kind], queryFn: () => fetchHealth(kind), refetchInterval: 15000 });
  return <div className="service"><span>{title}</span><strong role="status" className={query.isSuccess ? 'good' : 'muted'}>
    <i />{query.isPending ? '检查中' : query.isSuccess ? '运行正常' : '尚未就绪'}</strong></div>;
}
function App() {
  const [tab, setTab] = useState('工作台');
  return <div className="layout">
    <aside><a className="brand" href="/" aria-label="WeChat Data Hub 首页"><span className="logo">W<span>·</span></span><span>WeChat<br/><b>DATA HUB</b></span></a>
      <div className="nav-label">工作空间</div><nav>{['工作台', '开发进度', '隐私与边界'].map((item, i) =>
        <button key={item} className={tab === item ? 'active' : ''} onClick={() => setTab(item)} aria-current={tab === item ? 'page' : undefined}>
          <span aria-hidden="true">{['◫', '≡', '◇'][i]}</span>{item}</button>)}</nav>
      <div className="local"><span className="dot"/>本地优先<span>无遥测 · 无外部 AI</span></div>
    </aside>
    <div className="main"><header><span>本地工作空间 <span className="slash">/</span> {tab}</span><span className="version">v0.1.0 <i>开发中</i></span></header>
      <main><div className="eyebrow">YOUR DATA, YOUR CONTEXT</div><h1>{tab === '工作台' ? '让每一条记录，都有来处。' : tab}</h1>
        <p className="intro">私有保存，逐条追溯。为多设备聊天记录建立可信的数据底座。</p>
        {tab === '工作台' ? <>
          <section className="hero"><div><span className="tag">工程基础阶段 · P0 / P1</span><h2>你的数据，留在你的掌控中</h2><p>项目已进入开发。当前版本提供服务健康检查和工程基础，<br className="desktop"/>消息导入、浏览与审核将在后续阶段开放。</p><button onClick={() => setTab('开发进度')}>查看开发进度 <span>↗</span></button></div><div className="archive" aria-hidden="true"><div className="archive-back"/><div className="archive-front"><span>W</span><small>PRIVATE ARCHIVE</small><div>••• ━━━━━<br/>••• ━━━<br/>••• ━━━━━</div></div><div className="archive-badge">✓ 原始证据优先</div></div></section>
          <div className="section-heading"><h2>工作空间状态</h2><span>来自当前服务的实时检查</span></div>
          <section className="status-grid"><article><span className="card-icon">⌁</span><h3>服务连接</h3><Status title="API 服务" kind="live"/><Status title="数据库迁移" kind="ready"/></article>
            <article><span className="card-icon">▤</span><h3>数据归档</h3><p>尚未开放导入</p><small>完成原件归档、权限与导入验收后开放。</small></article>
            <article><span className="card-icon">◇</span><h3>来源兼容性</h3><p>等待真实样本验证</p><small>合成示例不代表真实微信兼容性通过。</small></article></section>
          <section className="note"><span>↳</span><div><h3>从原始文件开始，保留完整证据链</h3><p>系统接收用户合法取得的导出文件。官方加密备份保留为恢复资产；消息解析能力以实际验收为准。</p></div><span className="outline-tag">LOCAL FIRST</span></section>
        </> : tab === '开发进度' ? <section className="detail"><h2>当前交付范围</h2><ol><li>WDH-000：单仓库、API / React 框架、CI 与开发命令</li><li>WDH-001：来源边界、架构决策和许可评估记录</li><li>WDH-002：可复现的多设备合成边界样例</li><li>WDH-010：Bronze 数据库迁移与约束验证</li></ol><p>此页说明开发范围；实际 PASS / BLOCKED 和测试证据见仓库 TASKS.md 与 docs/TEST_EVIDENCE.md。</p><p>后续：原件 CAS → 格式适配器 → 持久导入任务 → 规范消息 → 权限与浏览。</p></section>
          : <section className="detail"><h2>默认私有，按证据处理</h2><p>OCR、ASR、语义检索、LLM、云对象存储和 Odoo 默认关闭。当前尚无这些集成。</p><p>不进行客户端注入、内存扫描、密钥提取或加密绕过。仅处理有权导入的导出文件。</p><p>消息、附件和原始数据接口将在权限隔离完成并通过测试后开放。</p></section>}
        <footer><span>WeChat Data Hub</span><span>可追溯 ≠ 数据源完整</span></footer>
      </main></div>
  </div>;
}
createRoot(document.getElementById('root')!).render(<QueryClientProvider client={queryClient}><App/></QueryClientProvider>);
