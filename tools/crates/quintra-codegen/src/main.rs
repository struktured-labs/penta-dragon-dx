//! quintra-codegen — emit GBDK C tables from content/.

use std::path::PathBuf;

use anyhow::{Context, Result};
use clap::Parser;

mod content;
mod emit;

#[derive(Parser, Debug)]
#[command(name = "quintra-codegen")]
struct Args {
    /// (informational) path to content/
    #[arg(long, default_value = "content")]
    content: PathBuf,

    /// Where to write generated C/H files
    #[arg(long, default_value = "src/generated")]
    out: PathBuf,
}

fn main() -> Result<()> {
    let args = Args::parse();
    std::fs::create_dir_all(&args.out)
        .with_context(|| format!("create out dir {}", args.out.display()))?;

    let reg = content::build_registry();
    if let Err(errs) = reg.validate() {
        eprintln!("quintra-codegen: content validation FAILED:");
        for e in &errs { eprintln!("  - {e}"); }
        std::process::exit(1);
    }

    emit::write_all(&args.out, &reg)?;

    println!(
        "quintra-codegen: ok — {} classes, {} items, {} enemies, {} biomes, {} rooms -> {}",
        reg.n_classes(), reg.n_items(), reg.n_enemies(), reg.n_biomes(),
        reg.n_room_templates(), args.out.display(),
    );
    Ok(())
}
