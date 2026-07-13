export type NavItem = {
  /** Fallback label when labelKey is not set (legacy portals). */
  label?: string;
  /** i18n key resolved in PortalShell. */
  labelKey?: string;
  path: string;
};

export type PortalConfig = {
  portalName?: string;
  portalSubtitle?: string;
  portalNameKey?: string;
  portalSubtitleKey?: string;
  basePath: string;
  navItems: NavItem[];
};
