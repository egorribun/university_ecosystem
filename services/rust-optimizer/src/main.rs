use axum::{
    extract::Json as AxumJson,
    http::StatusCode,
    routing::{get, post},
    Router,
};
use chrono::{DateTime, Utc, TimeZone, Datelike};
use serde::{Deserialize, Serialize};
use opentelemetry::KeyValue;
use opentelemetry_otlp::WithExportConfig;
use opentelemetry_sdk::{runtime, trace as sdktrace, Resource};
use std::env;
use std::net::SocketAddr;
use std::sync::Arc;
use tokio::signal;
use tracing::info;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};
use tonic::{transport::Server, Request, Response, Status};
use rayon::prelude::*;

// Import generated proto modules
pub mod optimizer {
    tonic::include_proto!("university_ecosystem.optimizer.v1");
}

use optimizer::optimizer_service_server::{OptimizerService, OptimizerServiceServer};
use optimizer::{
    BatchDetectConflictsRequest, BatchDetectConflictsResponse, DetectConflictsRequest,
    DetectConflictsResponse, FindOptimalSlotRequest, FindOptimalSlotResponse, ScheduleItem,
};

#[derive(Default)]
pub struct MyOptimizer {}

// In Rust 2024, we can use native async fn in traits directly
impl OptimizerService for MyOptimizer {
    async fn detect_conflicts(
        &self,
        request: Request<DetectConflictsRequest>,
    ) -> Result<Response<DetectConflictsResponse>, Status> {
        let req = request.into_inner();
        let target = req.target.ok_or_else(|| Status::invalid_argument("missing target"))?;

        let conflicts = req.existing
            .into_iter()
            .filter(|item| check_conflict_proto(&target, item))
            .collect();

        Ok(Response::new(DetectConflictsResponse { conflicts }))
    }

    async fn batch_detect_conflicts(
        &self,
        request: Request<BatchDetectConflictsRequest>,
    ) -> Result<Response<BatchDetectConflictsResponse>, Status> {
        let req = request.into_inner();
        let items = req.items;

        // Parallelize conflict detection using rayon
        let conflicts: Vec<optimizer::batch_detect_conflicts_response::ConflictPair> = items
            .par_iter()
            .enumerate()
            .flat_map(|(i, a)| {
                items[i + 1..]
                    .par_iter()
                    .filter(move |b| check_conflict_proto(a, b))
                    .map(move |b| optimizer::batch_detect_conflicts_response::ConflictPair {
                        item_a: Some(a.clone()),
                        item_b: Some(b.clone()),
                    })
            })
            .collect();

        Ok(Response::new(BatchDetectConflictsResponse { conflicts }))
    }

    async fn find_optimal_slot(
        &self,
        request: Request<FindOptimalSlotRequest>,
    ) -> Result<Response<FindOptimalSlotResponse>, Status> {
        let req = request.into_inner();
        let existing = req.existing_schedule;

        // Simple greedy solver: Try Monday-Friday, 9:00-18:00
        let days = if req.preferred_weekdays.is_empty() {
            vec!["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        } else {
            req.preferred_weekdays.iter().map(|s| s.as_str()).collect()
        };

        for day in days {
            // Try starts at 9, 11, 13, 15 (simplified)
            for hour in [9, 11, 13, 15] {
                // Fix: Use current year instead of hardcoded 2026
                let now = Utc::now();
                let current_year = now.year();

                // Construct time for the current year
                let start_time = Utc.with_yml_d(current_year, 1, 1).and_hms_opt(hour, 0, 0)
                    .ok_or_else(|| Status::internal("Failed to construct start time"))?;
                let end_time = start_time + chrono::Duration::minutes(req.duration_minutes as i64);

                let candidate = ScheduleItem {
                    id: None,
                    weekday: day.to_string(),
                    start_time: Some(prost_types::Timestamp {
                        seconds: start_time.timestamp(),
                        nanos: 0,
                    }),
                    end_time: Some(prost_types::Timestamp {
                        seconds: end_time.timestamp(),
                        nanos: 0,
                    }),
                    parity: "both".to_string(),
                    room: "Auto".to_string(),
                    teacher: "Auto".to_string(),
                };

                if !existing.iter().any(|item| check_conflict_proto(&candidate, item)) {
                    return Ok(Response::new(FindOptimalSlotResponse {
                        suggested_slot: Some(candidate),
                        status: "FOUND".to_string(),
                    }));
                }
            }
        }

        Ok(Response::new(FindOptimalSlotResponse {
            suggested_slot: None,
            status: "NOT_FOUND".to_string(),
        }))
    }
}

// REST models (compatible with existing Python code if needed)
#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct ScheduleItemRest {
    pub id: Option<i32>,
    pub weekday: String,
    pub start_time: DateTime<Utc>,
    pub end_time: DateTime<Utc>,
    pub parity: String,
}

#[derive(Deserialize)]
struct ConflictRequestRest {
    target: ScheduleItemRest,
    existing: Vec<ScheduleItemRest>,
}

#[derive(Serialize)]
struct ConflictResponseRest {
    conflicts: Vec<ScheduleItemRest>,
}

async fn detect_conflicts_rest(
    AxumJson(payload): AxumJson<ConflictRequestRest>,
) -> AxumJson<ConflictResponseRest> {
    let target = payload.target;
    let conflicts = payload
        .existing
        .into_iter()
        .filter(|item| {
            if target.weekday != item.weekday { return false; }
            let parity_conflict = target.parity == "both" || item.parity == "both" || target.parity == item.parity;
            if !parity_conflict { return false; }
            target.start_time < item.end_time && item.start_time < target.end_time
        })
        .collect();

    AxumJson(ConflictResponseRest { conflicts })
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let sentry_dsn = env::var("SENTRY_DSN").unwrap_or_default();
    let environment = env::var("VITE_ENVIRONMENT").unwrap_or_else(|_| "development".to_string());

    // Initialize Sentry
    let _guard = if !sentry_dsn.is_empty() {
        Some(sentry::init((
            sentry_dsn,
            sentry::ClientOptions {
                release: sentry::release_name!(),
                environment: Some(environment.clone().into()),
                traces_sample_rate: 1.0,
                ..Default::default()
            },
        )))
    } else {
        None
    };

    // Initialize OTEL
    let tracer = opentelemetry_otlp::new_pipeline()
        .tracing()
        .with_exporter(opentelemetry_otlp::new_exporter().tonic())
        .with_trace_config(sdktrace::config().with_resource(Resource::new(vec![
            KeyValue::new("service.name", "rust-optimizer"),
        ])))
        .install_batch(runtime::Tokio)?;

    tracing_subscriber::registry()
        .with(tracing_subscriber::fmt::layer())
        .with(tracing_opentelemetry::layer().with_tracer(tracer))
        .init();

    // Start gRPC server
    let grpc_addr = "[0.0.0.0]:50051".parse()?;
    let optimizer_service = MyOptimizer::default();

    info!("Starting gRPC server on {}", grpc_addr);
    let grpc_server = Server::builder()
        .add_service(OptimizerServiceServer::new(optimizer_service))
        .serve(grpc_addr);

    // Start REST server (Axum)
    let rest_addr = SocketAddr::from(([0, 0, 0, 0], 8080));
    let (prometheus_layer, metric_handle) = axum_prometheus::PrometheusMetricLayer::pair();
    let rest_app = Router::new()
        .route("/health", get(|| async { "OK" }))
        .route("/detect-conflicts", post(detect_conflicts_rest))
        .route("/metrics", get(|| async move { metric_handle.render() }))
        .layer(prometheus_layer);

    info!("Starting REST server on {}", rest_addr);
    let rest_server = axum::serve(tokio::net::TcpListener::bind(rest_addr).await?, rest_app);

    // Run both servers concurrently
    tokio::select! {
        res = grpc_server => res?,
        res = rest_server => res?,
        _ = shutdown_signal() => info!("Shutdown signal received"),
    }

    Ok(())
}

async fn shutdown_signal() {
    let ctrl_c = async {
        signal::ctrl_c().await.expect("failed to install Ctrl+C handler");
    };
    #[cfg(unix)]
    let terminate = async {
        signal::unix::signal(signal::unix::SignalKind::terminate()).expect("failed").recv().await;
    };
    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();
    tokio::select! { _ = ctrl_c => {}, _ = terminate => {} }
}
