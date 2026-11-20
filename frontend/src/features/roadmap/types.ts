export type RoadmapWeek = {
  week: number;
  title: string;
  description: string;
  deliverable: string;
  /** 이 주차가 메우는 역량 격차 (오른쪽 작은 글) */
  gap: string;
};

export type Roadmap = {
  targetRole: string;
  basis: string;
  order: string[];
  weeks: RoadmapWeek[];
};
