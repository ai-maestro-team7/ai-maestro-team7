export type AsyncStatus =
  | "PENDING"
  | "PROCESSING"
  | "REQUIRES_USER_REVIEW"
  | "PARTIAL_SUCCESS"
  | "COMPLETED"
  | "FAILED";

export type Warning = { code: string; message: string };

export type CreateDocumentResponse = {
  documentId: string;
  version: number;
  taskId: string;
  status: AsyncStatus;
  extractionStatus: string;
};

export type DocumentResponse = {
  documentId: string;
  extractionStatus: string;
  taskStatus?: AsyncStatus;
  /** 추출한 글자 수. 추출 전에는 없다 */
  charCount?: number;
};

export type ProfileResponse = {
  profileId: string;
  profileVersion: number;
};

export type Evidence = { evidenceId: string; quotedText: string };

export type RequirementMatch = {
  requirementId?: string;
  name?: string;
  category?: string;
  evidenceLevel?: string;
  kind?: string;
  type?: string;
  result?: string;
  reason?: string;
  sourceQuote?: string;
  evidenceIds?: string[];
  evidence?: Evidence[];
  question?: string;
};

export type Source = {
  documentId: string;
  documentType?: string;
  role?: string;
  sourceUrl?: string;
  checkedAt?: string;
  excerpt?: string;
};

export type AnalysisResponse = {
  analysisId: string;
  status: AsyncStatus;
  taskId?: string;
  assessmentMode?: string;
  profileId?: string;
  profileVersion?: number;
  ncs?: { code: string; name: string };
  eligibility?: { status: string };
  scoreStatus?: string;
  fitScore?: number | null;
  potentialUpperBound?: number | null;
  scorePolicyVersion?: string;
  strengths?: RequirementMatch[];
  partialEvidence?: RequirementMatch[];
  unverifiedSkills?: RequirementMatch[];
  confirmedGaps?: RequirementMatch[];
  summary?: string;
  sources?: Source[];
  warnings?: Warning[];
  sourceCheckedAt?: string;
  reviewReason?: string;
  nextAction?: string;
};

export type CreateResourceResponse = {
  status: AsyncStatus;
  taskId: string;
  analysisId?: string;
  reviewId?: string;
  learningPathId?: string;
};

export type ReviewIssue = {
  issueId: string;
  sourceSpan?: { startChar: number; endChar: number };
  originalText?: string;
  issueType: string;
  reason: string;
  improvementAction: string;
  revisedExample?: string;
  needsUserConfirmation: boolean;
  questions: string[];
  factCheck: string;
  detectedBy?: string;
};

export type ReviewResponse = {
  reviewId: string;
  status: AsyncStatus;
  documentType?: string;
  analysisId?: string;
  questionText?: string;
  maxCharacters?: number;
  factCheckStatus?: string;
  questionIntent?: string;
  overallFeedback?: string;
  strengths?: string[];
  issues?: ReviewIssue[];
  missingQuestions?: string[];
  charCount?: {
    withSpaces: number;
    withoutSpaces: number;
    utf8Bytes: number;
    maxCharacters?: number;
    overLimit: boolean;
  };
  warnings?: Warning[];
};

export type LearningTarget = {
  targetId: string;
  kind: string;
  name: string;
  category?: string;
  requirementId?: string;
  ncsUnitCode?: string;
};

export type LearningWeek = {
  week: number;
  startDate: string;
  targetIds: string[];
  goals: string[];
  activities: string[];
  deliverable: string;
  estimatedHours: number;
  officialSources: Array<{ type: string; unitCode?: string; name?: string; url?: string }>;
};

export type CertificateCandidate = {
  qualificationCode: string;
  name: string;
  examAgency?: string;
  reason: string;
  requiredByPosting: boolean;
  verificationStatus: string;
  officialUrl?: string;
  checkedAt?: string;
  schedule?: Array<{ round: string; resultAfterPostingDeadline?: boolean }>;
};

export type LearningPathResponse = {
  learningPathId: string;
  status: AsyncStatus;
  analysisId?: string;
  ncsCode?: string;
  ncsName?: string;
  weeklyStudyHours?: number;
  preferredFormat?: string;
  startDate?: string;
  targetDate?: string;
  totalWeeks?: number;
  totalHours?: number;
  estimated?: boolean;
  targets?: LearningTarget[];
  verificationTasks?: Array<{ name: string; question?: string }>;
  weeks?: LearningWeek[];
  certificates?: CertificateCandidate[];
  courses?: Array<{ title?: string; officialUrl?: string; checkedAt?: string }>;
  sourceVerificationStatus?: Record<string, string>;
  relatedLinks?: Array<{ type: string; path?: string; url?: string; label: string }>;
  warnings?: Warning[];
};

export type MentoringFlow = {
  targetRole: string;
  targetNcsCode: string;
  documentId: string;
  profileId: string;
  profileVersion: number;
  analysisId: string;
  workspaceId?: string;
  reviewId?: string;
  learningPathId?: string;
};
