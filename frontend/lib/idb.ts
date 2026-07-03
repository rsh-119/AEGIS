/**
 * Thin IndexedDB wrapper for SWR cache persistence.
 * All calls are fire-and-forget safe — errors are swallowed so they
 * never crash the UI.
 */

const DB_NAME = "aegis";
const STORE   = "swr-cache";
const VERSION = 1;

let _db: IDBDatabase | null = null;

function openDB(): Promise<IDBDatabase> {
  if (_db) return Promise.resolve(_db);
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, VERSION);
    req.onupgradeneeded = () => {
      req.result.createObjectStore(STORE);
    };
    req.onsuccess = () => {
      _db = req.result;
      resolve(req.result);
    };
    req.onerror = () => reject(req.error);
  });
}

export async function idbGet<T = unknown>(key: string): Promise<T | undefined> {
  try {
    const db = await openDB();
    return new Promise((res, rej) => {
      const req = db.transaction(STORE, "readonly").objectStore(STORE).get(key);
      req.onsuccess = () => res(req.result as T);
      req.onerror   = () => rej(req.error);
    });
  } catch {
    return undefined;
  }
}

export async function idbSet(key: string, val: unknown): Promise<void> {
  try {
    const db = await openDB();
    await new Promise<void>((res, rej) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).put(val, key);
      tx.oncomplete = () => res();
      tx.onerror    = () => rej(tx.error);
    });
  } catch {
    // ignore — storage may be full or private browsing
  }
}

export async function idbDelete(key: string): Promise<void> {
  try {
    const db = await openDB();
    await new Promise<void>((res, rej) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).delete(key);
      tx.oncomplete = () => res();
      tx.onerror    = () => rej(tx.error);
    });
  } catch {}
}

/** Read all entries at once for cache hydration. */
export async function idbGetAll(): Promise<Record<string, unknown>> {
  try {
    const db = await openDB();
    return new Promise((res, rej) => {
      const result: Record<string, unknown> = {};
      const tx = db.transaction(STORE, "readonly");
      const req = tx.objectStore(STORE).openCursor();
      req.onsuccess = () => {
        const cur = req.result;
        if (cur) {
          result[cur.key as string] = cur.value;
          cur.continue();
        } else {
          res(result);
        }
      };
      req.onerror = () => rej(req.error);
    });
  } catch {
    return {};
  }
}

/** Clear all cached entries (e.g. on logout or manual refresh). */
export async function idbClear(): Promise<void> {
  try {
    const db = await openDB();
    await new Promise<void>((res, rej) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).clear();
      tx.oncomplete = () => res();
      tx.onerror    = () => rej(tx.error);
    });
  } catch {}
}
