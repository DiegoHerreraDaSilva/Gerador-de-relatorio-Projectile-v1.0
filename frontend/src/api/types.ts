export type Activity = {
  id: string;
  description: string;
  hours: number | null;
};

export type Group = {
  id: string;
  name: string;
  performance: number;
  activities: Activity[];
};

export type WorkPackage = {
  id: string;
  key: string;
  projectCode: string;
  projectName: string;
  groups: Group[];
  collapsedGroupIds: Set<string>;
  fileName: string;
  fileNameEdited: boolean;
};

export type RowIssue = {
  row: number;
  reason: string;
  message: string;
};

export type ReportHeader = {
  locationDate: string;
  monthLabel: string;
  signer1Name: string;
  signer1Company: string;
  signer2Name: string;
  signer2Company: string;
};

export type ParseResponse = {
  packages: Array<{
    key: string;
    project_name: string;
    groups: Array<{
      name: string;
      total_hours: number;
      activities: Array<{ description: string; hours: number }>;
    }>;
  }>;
  issues: RowIssue[];
};

export type GeneratePackagePayload = {
  header: {
    project_code: string;
    project_name: string;
    location_date: string;
    month_label: string;
    signer1_name: string;
    signer1_company: string;
    signer2_name: string;
    signer2_company: string;
  };
  groups: Array<{
    name: string;
    performance: number;
    activities: Array<{ description: string; hours: number | null }>;
  }>;
  file_name?: string;
};

export type ChatStatePayload = {
  packages: Array<{
    key: string;
    projectCode: string;
    projectName: string;
    groups: Array<{
      name: string;
      performance: number;
      activities: Array<{ description: string; hours: number | null }>;
    }>;
  }>;
  activePackageIndex: number;
  locationDate: string;
  monthLabel: string;
  signer1Name: string;
  signer1Company: string;
  signer2Name: string;
  signer2Company: string;
};
