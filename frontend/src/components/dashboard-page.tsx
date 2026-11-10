import Link from "next/link";
import {
  ArrowDownToLine,
  ArrowRight,
  BarChart3,
  Boxes,
  CircleDollarSign,
  MapPinned,
  PackageSearch,
  ShoppingCart,
  Sparkles,
  Users,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";

const metrics = [
  { label: "Total sales", icon: BarChart3 },
  { label: "Total profit", icon: CircleDollarSign },
  { label: "Profit margin", icon: Sparkles },
  { label: "Total orders", icon: ShoppingCart },
  { label: "Total customers", icon: Users },
  { label: "Total products", icon: Boxes },
];

function EmptyChart({
  title,
  icon: Icon,
  className,
}: {
  title: string;
  icon: typeof BarChart3;
  className?: string;
}) {
  return (
    <Card className={cn("panel-card", className)}>
      <CardHeader className="panel-header">
        <div>
          <CardTitle className="panel-title">{title}</CardTitle>
          <p className="panel-subtitle">Your data will appear here after import</p>
        </div>
        <Button variant="ghost" size="icon-sm" aria-label={`${title} options`} disabled title="Connect a dataset to enable chart options">
          <ArrowDownToLine />
        </Button>
      </CardHeader>
      <CardContent>
        <div className="chart-empty" role="status" aria-label={`${title}: no dataset connected`}>
          <div className="chart-grid" aria-hidden="true">
            <span />
            <span />
            <span />
            <span />
          </div>
          <div className="chart-empty-message">
            <span className="chart-empty-icon"><Icon aria-hidden="true" /></span>
            <span className="chart-empty-title">Waiting for your data</span>
            <span className="chart-empty-copy">Upload a dataset to generate this visualization.</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function EmptyList({
  title,
  icon: Icon,
  linkLabel,
  href,
}: {
  title: string;
  icon: typeof BarChart3;
  linkLabel: string;
  href: string;
}) {
  return (
    <Card className="panel-card">
      <CardHeader className="panel-header">
        <div>
          <CardTitle className="panel-title">{title}</CardTitle>
          <p className="panel-subtitle">Based on your connected business data</p>
        </div>
        <Link href={href} className="panel-link">{linkLabel}<ArrowRight aria-hidden="true" /></Link>
      </CardHeader>
      <CardContent>
        <div className="list-empty" role="status">
          <span className="empty-icon"><Icon aria-hidden="true" /></span>
          <span className="empty-title">Nothing to show yet</span>
          <span className="empty-copy">Connect a dataset to see live results here.</span>
        </div>
      </CardContent>
    </Card>
  );
}

export function DashboardPage() {
  return (
    <div className="page-stack">
      <section className="page-heading-row">
        <div>
          <p className="eyebrow">Your business, at a glance</p>
          <h1 className="page-title">Overview dashboard</h1>
          <p className="page-description">A clear view of what is happening across your business.</p>
        </div>
        <div className="page-actions">
          <Link href="/export-center" className={cn(buttonVariants({ variant: "outline", size: "lg" }), "action-button") }>
            <ArrowDownToLine data-icon="inline-start" /> Export report
          </Link>
          <Link href="/upload" className={cn(buttonVariants({ size: "lg" }), "action-button") }>
            <span className="plus-mark" aria-hidden="true">+</span> Import data
          </Link>
        </div>
      </section>

      <div className="connection-banner" role="status">
        <span className="connection-indicator" aria-hidden="true" />
        <span className="connection-copy"><strong>Python analytics adapter</strong><span>Upload a dataset to run the existing RetailMind analytics functions.</span></span>
        <Badge variant="outline" className="status-badge">Local · in-memory</Badge>
        <Link href="/data-connections" className="connection-link">Connection settings <ArrowRight aria-hidden="true" /></Link>
      </div>

      <section aria-label="Business performance metrics" className="metric-grid">
        {metrics.map(({ label, icon: Icon }) => (
          <Card className="metric-card" key={label}>
            <CardContent className="metric-content">
              <div className="metric-topline">
                <span className="metric-label">{label}</span>
                <span className="metric-icon"><Icon aria-hidden="true" /></span>
              </div>
              <div className="metric-value" aria-label={`${label}: not available`}>—</div>
              <div className="metric-footnote">Available after dataset connection</div>
            </CardContent>
          </Card>
        ))}
      </section>

      <section className="dashboard-grid dashboard-grid-primary" aria-label="Business trends and summary">
        <EmptyChart title="Sales vs. profit trends" icon={BarChart3} />
        <Card className="panel-card summary-card">
          <CardHeader className="panel-header">
            <div>
              <CardTitle className="panel-title">Business performance</CardTitle>
              <p className="panel-subtitle">A summary of your current reporting period</p>
            </div>
            <Badge variant="secondary">Overview</Badge>
          </CardHeader>
          <CardContent>
            <div className="summary-placeholder">
              <div className="summary-ring"><Sparkles aria-hidden="true" /></div>
              <p className="empty-title">Your summary starts here</p>
              <p className="empty-copy">Connect a dataset to calculate sales, profit, and growth from real records.</p>
              <Link href="/upload" className="text-action">Add your first dataset <ArrowRight aria-hidden="true" /></Link>
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="dashboard-grid dashboard-grid-secondary" aria-label="Product and location analytics">
        <EmptyChart title="Category-wise sales" icon={Boxes} />
        <EmptyList title="Top performing products" icon={PackageSearch} linkLabel="View products" href="/product-analytics" />
        <EmptyList title="City-wise performance" icon={MapPinned} linkLabel="View cities" href="/city-analytics" />
      </section>

      <section className="dashboard-grid dashboard-grid-bottom" aria-label="Recent transactions and AI insights">
        <Card className="panel-card">
          <CardHeader className="panel-header">
            <div>
              <CardTitle className="panel-title">Recent transactions</CardTitle>
              <p className="panel-subtitle">The latest activity from your sales data</p>
            </div>
            <Link href="/sales-analytics" className="panel-link">View analytics<ArrowRight aria-hidden="true" /></Link>
          </CardHeader>
          <CardContent>
            <div className="table-empty" role="status">
              <ShoppingCart aria-hidden="true" />
              <span>No transactions loaded</span>
              <span>Import sales data to review order-level activity.</span>
            </div>
          </CardContent>
        </Card>
        <Card className="insight-card">
          <CardHeader className="panel-header">
            <div>
              <CardTitle className="panel-title">AI business insights</CardTitle>
              <p className="panel-subtitle">Grounded in your actual dataset</p>
            </div>
            <Sparkles className="insight-sparkle" aria-hidden="true" />
          </CardHeader>
          <CardContent>
            <div className="insight-body">
              <div className="insight-icon"><Sparkles aria-hidden="true" /></div>
              <div>
                <p className="insight-title">Insights are ready when your data is</p>
                <p className="insight-copy">RetailMind uses your existing analytics logic. No business figures are generated before a dataset is connected.</p>
              </div>
            </div>
            <Link href="/business-insights" className="insight-link">Explore business insights<ArrowRight aria-hidden="true" /></Link>
          </CardContent>
        </Card>
      </section>

      <div className="dashboard-footnote">No sample figures are shown. Dashboard calculations will come from your imported dataset.</div>
    </div>
  );
}
