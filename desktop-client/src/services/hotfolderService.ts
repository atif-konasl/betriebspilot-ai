/**
 * BetriebsPilot AI - Local Hotfolder File Writer Service
 * Handles direct writing of XML / JSON ERP payloads into the local legacy ERP watch-folder.
 */

export interface ExportResult {
  success: boolean;
  filePath: string;
  message: string;
}

export class HotfolderService {
  private defaultFolder: string;

  constructor() {
    // Default legacy ERP import watchfolder paths
    const isWindows = typeof navigator !== 'undefined' && navigator.userAgent.includes('Windows');
    this.defaultFolder = isWindows ? 'C:\\ERP_Import\\Incoming_Orders' : '/tmp/erp_import';
  }

  getDefaultFolder(): string {
    return this.defaultFolder;
  }

  /**
   * Writes the generated ERP payload (OpenTRANS XML or SAP B1 JSON) into the target directory.
   * If running in Tauri, writes natively to disk.
   * If running in web browser, triggers automatic file download.
   */
  async exportFile(
    fileName: string,
    content: string,
    targetDirectory: string = this.defaultFolder
  ): Promise<ExportResult> {
    const fullPath = `${targetDirectory.replace(/\\$/, '').replace(/\/$/, '')}/${fileName}`;

    try {
      // 1. Check if running inside native Tauri runtime
      // @ts-ignore
      if (typeof window !== 'undefined' && window.__TAURI_INTERNALS__) {
        // Native Tauri write logic
        try {
          // Dynamic import of Tauri FS plugin if available
          // @ts-ignore
          const { writeTextFile } = await import('@tauri-apps/plugin-fs');
          await writeTextFile(fullPath, content);
          return {
            success: true,
            filePath: fullPath,
            message: `Datei erfolgreich direkt im ERP-Hotfolder abgelegt: ${fullPath}`,
          };
        } catch (tauriErr) {
          console.warn('Tauri native write failed, falling back to download:', tauriErr);
        }
      }

      // 2. Web Browser Fallback: Trigger Blob Download
      const mimeType = fileName.endsWith('.xml') ? 'application/xml' : 'application/json';
      const blob = new Blob([content], { type: mimeType });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      return {
        success: true,
        filePath: fullPath,
        message: `ERP-Datei generiert & heruntergeladen (Ziel: ${fullPath})`,
      };
    } catch (err: any) {
      console.error('Hotfolder write failed:', err);
      return {
        success: false,
        filePath: fullPath,
        message: `Fehler beim Schreiben in ERP-Hotfolder: ${err.message || String(err)}`,
      };
    }
  }
}

export const hotfolderService = new HotfolderService();
