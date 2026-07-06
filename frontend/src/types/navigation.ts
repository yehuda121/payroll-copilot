export type NavItem = {
  label: string;
  path: string;
};

export type PortalConfig = {
  portalName: string;
  portalSubtitle: string;
  basePath: string;
  navItems: NavItem[];
};
