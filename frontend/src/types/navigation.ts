export type NavItem = {
  /** Fallback label when labelKey is not set (legacy portals). */
  label?: string;
  /** i18n key resolved in PortalShell. */
  labelKey?: string;
  path: string;
  /** Optional backend-backed unseen badge (e.g. vacations). */
  badgeKey?: 'vacationsUnseen' | 'sickLeavesUnseen';
};

/** Optional sidebar group for domain-organized portals (e.g. System Admin). */
export type NavGroup = {
  /** i18n key for the group heading. */
  labelKey: string;
  items: NavItem[];
};

export type PortalConfig = {
  portalName?: string;
  portalSubtitle?: string;
  portalNameKey?: string;
  portalSubtitleKey?: string;
  basePath: string;
  navItems: NavItem[];
  /** When set, PortalShell renders grouped navigation instead of a flat list. */
  navGroups?: NavGroup[];
  /** When true, show the authenticated user's email above the sidebar nav. */
  showUserEmail?: boolean;
};
