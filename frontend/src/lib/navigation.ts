import type { LucideIcon } from "lucide-react";
import {
  Bell,
  Bot,
  Boxes,
  BriefcaseBusiness,
  Building2,
  CircleDollarSign,
  Clock3,
  Database,
  FileBarChart2,
  FileSpreadsheet,
  FileText,
  Gauge,
  Layers,
  Lightbulb,
  MapPinned,
  PackageSearch,
  PanelTop,
  Settings2,
  ShieldCheck,
  ShoppingBag,
  Sparkles,
  Tags,
  Target,
  TrendingUp,
  Upload,
  Users,
  UserRound,
  Wrench,
} from "lucide-react";

export type NavigationItem = {
  label: string;
  href: string;
  icon: LucideIcon;
  description: string;
};

export type NavigationGroup = {
  label: string;
  items: NavigationItem[];
};

export const navigationGroups: NavigationGroup[] = [
  {
    label: "Workspace",
    items: [
      { label: "Overview Dashboard", href: "/overview", icon: PanelTop, description: "A clear view of your business performance." },
      { label: "My Datasets", href: "/datasets", icon: Database, description: "Review datasets available in this workspace." },
      { label: "Data Upload", href: "/upload", icon: Upload, description: "Bring a CSV or Excel workbook into RetailMind." },
      { label: "Recent Activity", href: "/activity", icon: Clock3, description: "See recent work across your analytics workspace." },
    ],
  },
  {
    label: "Business analytics",
    items: [
      { label: "Sales Analytics", href: "/sales-analytics", icon: TrendingUp, description: "Explore revenue patterns and sales performance." },
      { label: "Profitability Analytics", href: "/profitability-analytics", icon: CircleDollarSign, description: "Understand profit, cost, and margin drivers." },
      { label: "Product Analytics", href: "/product-analytics", icon: ShoppingBag, description: "Compare products and identify performance gaps." },
      { label: "Category Analytics", href: "/category-analytics", icon: Boxes, description: "Review performance across product categories." },
      { label: "Visual Analytics", href: "/visual-analytics", icon: Layers, description: "Explore 20+ advanced charts with cross-filtering." },
      { label: "India Map", href: "/india-map", icon: MapPinned, description: "Analyse state and city performance on a map." },
      { label: "Customer Analytics", href: "/customer-analytics", icon: Users, description: "Understand customers, orders, and retention." },
      { label: "City-wise Analytics", href: "/city-analytics", icon: MapPinned, description: "Compare business performance by city." },
      { label: "Inventory Analytics", href: "/inventory-analytics", icon: PackageSearch, description: "Monitor stock health and replenishment needs." },
      { label: "Goals & Targets", href: "/goals", icon: Target, description: "Set user-scoped sales and profit targets." },
    ],
  },
  {
    label: "AI intelligence",
    items: [
      { label: "AI Business Assistant", href: "/assistant", icon: Bot, description: "Ask questions grounded in your business data." },
      { label: "RAG Knowledge Assistant", href: "/rag-assistant", icon: Sparkles, description: "Search business documents with source references." },
      { label: "Smart Business Insights", href: "/business-insights", icon: Lightbulb, description: "Surface notable changes and opportunities." },
      { label: "Smart Alerts", href: "/smart-alerts", icon: Bell, description: "Review important business and inventory signals." },
      { label: "Automated Customer Tagging", href: "/customer-tagging", icon: Tags, description: "Create useful customer tags from real activity." },
      { label: "Customer Segmentation", href: "/customer-segmentation", icon: Users, description: "Explore customer groups and RFM behavior." },
    ],
  },
  {
    label: "Predictive analytics",
    items: [
      { label: "Sales Forecasting", href: "/sales-forecasting", icon: TrendingUp, description: "Project sales using the existing forecasting engine." },
      { label: "Profit Forecasting", href: "/profit-forecasting", icon: CircleDollarSign, description: "Estimate future profit from historical performance." },
      { label: "Predictive Stock Recommendations", href: "/stock-recommendations", icon: PackageSearch, description: "Plan reorder quantities and stock coverage." },
      { label: "Business Performance Predictions", href: "/performance-predictions", icon: Gauge, description: "Review a forward-looking business outlook." },
    ],
  },
  {
    label: "Reports & exports",
    items: [
      { label: "Saved Reports", href: "/saved-reports", icon: FileBarChart2, description: "Return to reports saved from your analysis." },
      { label: "Report Builder", href: "/report-builder", icon: Wrench, description: "Shape a report from selected analytics." },
      { label: "Export Center", href: "/export-center", icon: FileText, description: "Choose an output format for your analysis." },
      { label: "Excel Export", href: "/excel-export", icon: FileSpreadsheet, description: "Prepare a workbook from verified dataset results." },
      { label: "PDF Export", href: "/pdf-export", icon: FileText, description: "Prepare a shareable business report." },
      { label: "Power BI Export", href: "/power-bi-export", icon: BriefcaseBusiness, description: "Prepare a Power BI project package." },
      { label: "PBIP / TMDL / PBIR", href: "/pbip-export", icon: PanelTop, description: "Export a Power BI project, model, or report layout." },
      { label: "Markdown Export", href: "/markdown-export", icon: FileText, description: "Download a date-filtered Markdown report." },
    ],
  },
  {
    label: "Settings",
    items: [
      { label: "User Profile", href: "/profile", icon: UserRound, description: "Review your profile and workspace identity." },
      { label: "Account Settings", href: "/account-settings", icon: Settings2, description: "Manage account-level preferences." },
      { label: "Data Connections", href: "/data-connections", icon: Database, description: "Connect the separate Python analytics service." },
      { label: "Preferences", href: "/preferences", icon: Building2, description: "Choose how your workspace should behave." },
      { label: "Security", href: "/security", icon: ShieldCheck, description: "Review session and security settings." },
      { label: "Owner Admin", href: "/owner-admin", icon: ShieldCheck, description: "Review account, session, and audit controls." },
    ],
  },
];

export const allNavigationItems = navigationGroups.flatMap((group) =>
  group.items.map((item) => ({ ...item, group: group.label })),
);

export function getNavigationItem(section: string) {
  return allNavigationItems.find((item) => item.href.slice(1) === section);
}
