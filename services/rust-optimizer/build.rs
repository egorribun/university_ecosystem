fn main() -> Result<(), Box<dyn std::error::Error>> {
    tonic_build::configure()
        .compile_protos(
            &["../../proto/university_ecosystem/optimizer/v1/optimizer.proto"],
            &["../../proto"],
        )?;
    Ok(())
}
