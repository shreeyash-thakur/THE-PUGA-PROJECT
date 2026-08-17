export type Zone = "core" | "buffer" | "village-adjacent";

export interface Camera {
  camera_id: string;
  name: string;
  latitude: number;
  longitude: number;
  location_name: string;
  zone: Zone;
  /** ISO date the station was installed — used to suppress survey-effort artefacts. */
  installed_at: string;
}

export interface Tiger {
  tiger_id: string;
  name: string | null;
  status: "active" | "unknown" | "archived";
  first_seen: string | null;
  last_seen: string | null;
  total_sightings: number;
  reference_image?: string | null;
}

export interface Sighting {
  sighting_id: string;
  tiger_id: string;
  camera_id: string | null;
  timestamp: string;
  latitude: number | null;
  longitude: number | null;
  location_name: string | null;
  similarity_score: number | null;
  confidence: number | null;
  image_path?: string | null;
  crop_path?: string | null;
  /** Set when the automatic match was not confident enough. */
  review_status?: "auto" | "needs-review" | "confirmed";
}

export interface QuarantineItem {
  id: number;
  batch_id: string;
  filename: string;
  original_path: string;
  quarantine_path: string | null;
  status: "quarantined" | "restored";
  reason: string | null;
  confidence: number | null;
  capture_timestamp: string | null;
  quarantined_at: string;
  restored_at?: string | null;
  /** Frames containing people are blurred/withheld for privacy. */
  privacy_hold?: boolean;
}

export interface BatchSummary {
  batch_id: string;
  status: "running" | "completed" | "interrupted" | "failed";
  source_folder: string;
  total_images: number;
  processed: number;
  animal_detected: number;
  quarantined: number;
  duplicates: number;
  failed: number;
  restored: number;
  processing_time_seconds: number | null;
  storage: {
    original_storage_bytes: number;
    quarantine_storage_bytes: number;
    reclaimable_storage_bytes: number;
  };
  warnings: string[];
  created_at: string;
}
