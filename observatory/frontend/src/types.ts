export interface Run {
  test_id: string;
  created_at: string | number;
  updated_at: string | number;
  object_count: number;
  message_count: number;
  duplicate_count: number;
  quarantined_count: number;
  conflict_count: number;
  revision: number;
  received_objects: number;
  applied_objects: number;
}
export interface Frame {
  frame_id: string;
  frame_kind: string;
  unit: string;
  count: number;
}
export interface TypeNode {
  type_id: number;
  parent_id: number;
  name: string;
  object_count?: number;
  subtree_count?: number;
}
export interface Change {
  revision: number;
  changes: Array<{
    op: string;
    node: { type_id: number; parent_id: number; name: string };
  }>;
  received_at: string | number;
}
export interface TypeResponse {
  revision: number;
  items: TypeNode[];
  changes: Change[];
}
export interface Position {
  frame_id: string;
  frame_kind: string;
  unit: string;
  x: number;
  y: number;
  z: number;
}
export interface ObjectItem {
  row_id: number;
  id: string;
  name: string;
  type_id: number;
  type_name?: string;
  sequence: number;
  timestamp_ms: number;
  position: Position | null;
}
export interface Observation {
  id: string;
  name: string;
  type_id: number;
  sequence: number;
  timestamp_ms: number;
  position: Position | null;
  attributes: Record<string, unknown>;
  [key: string]: unknown;
}
export interface ObjectMetadata {
  row_id: number;
  tree_revision: number;
  received_at: string | number;
  type_name: string;
}
export interface ObjectDetail {
  object: Observation;
  meta: ObjectMetadata;
}
export interface ObjectPage {
  items: ObjectItem[];
  next_cursor: string | null;
  snapshot_max: number;
}
export interface Point {
  id: string;
  name: string;
  type_id: number;
  x: number;
  y: number;
  z: number;
}
export interface PointsResponse {
  items: Point[];
  frame: Frame;
  limit: number;
  sampled: boolean;
  total: number;
}
export interface Message {
  id: number;
  kind: string;
  message_key: string;
  status: string;
  reason: string | null;
  received_at: string | number;
  object_count: number;
  raw?: unknown;
  [key: string]: unknown;
}
export interface Metrics extends Run {
  rate_objects_per_second: number;
  rate_messages_per_second: number;
  database_bytes: number;
  storage_limit_bytes: number;
  backlog: number;
  frames: Frame[];
  categories: TypeNode[];
  recent_messages: Message[];
  uptime_seconds: number;
}
export interface Filters {
  type_id: string;
  name_prefix: string;
  object_id: string;
  frame_id: string;
  frame_kind: string;
  unit: string;
  descendants: boolean;
}
export const emptyFilters: Filters = {
  type_id: "",
  name_prefix: "",
  object_id: "",
  frame_id: "",
  frame_kind: "",
  unit: "",
  descendants: true,
};
