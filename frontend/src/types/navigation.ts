export type NavTabId = 'new-analysis' | 'workspace' | 'library' | 'review';

export interface NavItem {
  id: NavTabId;
  label: string;
  badge?: string;
  description: string;
}

export const NAV_ITEMS: NavItem[] = [
  {
    id: 'new-analysis',
    label: 'New Analysis',
    description: 'Start a new evidence-grounded research query'
  },
  {
    id: 'workspace',
    label: 'Analysis Workspace',
    description: 'View active investigations and multi-agent plans'
  },
  {
    id: 'library',
    label: 'Question Library',
    badge: '28 eval cases',
    description: 'Explore the validated pharmaceutical benchmark catalog'
  },
  {
    id: 'review',
    label: 'Human Review',
    badge: 'Safety',
    description: 'Triage queue for adverse event safety escalations'
  }
];
