part of 'main.dart';

// A farm-specific cache keeps offline edits. Server revisions prevent silent
// overwrites across devices; deletions are queued separately from updates.
abstract class _ParcelSyncState extends State<AgroPlanHome> {
  final parcels = <FarmParcel>[];
  final String cacheKey =
      'agroplan_parcels_v3_${Uri.encodeComponent(apiBaseUrl)}_${ApiSession.instance.farmId}';
  final pendingDeletes = <String, int>{};
  final pendingSoil = <Map<String, dynamic>>[];
  int soilRevision = 0;
  final savedPayloads = <String, String>{};
  final savedRevisions = <String, int>{};
  bool syncing = false;
  bool workspaceReady = false;
  Future<void>? workspaceCheck;
  bool syncAgain = false;
  String? syncError;
  int agronomyRevision = 0;

  String? get selectedId;
  set selectedId(String? value);
  void clearSatelliteOverlay();
  void clearWeather();
  Future<void> saveParcels();
}

mixin _ParcelSync on _ParcelSyncState {
  Future<void> verifyWorkspaceGeneration() async {
    if (workspaceCheck != null) return workspaceCheck!;
    final pending = verifyWorkspaceOnce();
    workspaceCheck = pending;
    try {
      await pending;
    } finally {
      if (identical(workspaceCheck, pending)) workspaceCheck = null;
    }
  }

  Future<void> verifyWorkspaceOnce() async {
    final response = await http
        .get(Uri.parse('$apiBaseUrl/workspace/status'))
        .timeout(const Duration(seconds: 75));
    if (response.statusCode != 200) {
      throw Exception(
        'Area di lavoro non verificabile. Collegati al server e riprova.',
      );
    }
    final data = jsonDecode(response.body) as Map;
    final generation = data['generation'];
    if (generation is! int) {
      throw const FormatException('Versione area di lavoro non valida.');
    }
    final prefs = await SharedPreferences.getInstance();
    final changed = await reconcileWorkspaceCache(
      prefs,
      cacheKey,
      'field_draft_${apiBaseUrl}_${ApiSession.instance.farmId}_',
      generation,
    );
    if (changed && mounted) {
      setState(() {
        parcels.clear();
        pendingDeletes.clear();
        pendingSoil.clear();
        savedPayloads.clear();
        savedRevisions.clear();
        selectedId = null;
        clearSatelliteOverlay();
        clearWeather();
      });
      await writeCache();
    }
    if (mounted) setState(() => workspaceReady = true);
  }

  String parcelPayload(FarmParcel parcel) {
    final data = parcel.toJson()
      ..remove('revision')
      ..remove('pending');
    return jsonEncode(data);
  }

  void rememberParcels() {
    savedPayloads
      ..clear()
      ..addEntries(parcels.map((p) => MapEntry(p.id, parcelPayload(p))));
    savedRevisions
      ..clear()
      ..addEntries(parcels.map((p) => MapEntry(p.id, p.revision)));
  }

  Future<void> writeCache() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      cacheKey,
      jsonEncode({
        'parcels': parcels.map((p) => p.toJson()).toList(),
        'deletions': pendingDeletes,
        'soilOutbox': pendingSoil,
      }),
    );
  }

  Future<void> restoreParcels() async {
    var offline = false;
    try {
      await verifyWorkspaceGeneration();
    } catch (_) {
      final prefs = await SharedPreferences.getInstance();
      if (!mounted) return;
      if (!prefs.containsKey('${cacheKey}_generation')) {
        setState(
          () => syncError = 'Collegati al server per verificare l’area di lavoro prima di caricare le particelle.',
        );
        return;
      }
      offline = true;
      setState(() {
        workspaceReady = true;
        syncError = 'Modalità offline: copia locale disponibile. Collegati per verificare gli aggiornamenti dell’area di lavoro.';
      });
    }
    try {
      final prefs = await SharedPreferences.getInstance();
      final saved = prefs.getString(cacheKey);
      if (!mounted) return;
      if (saved != null) {
        final data = jsonDecode(saved) as Map<String, dynamic>;
        final loaded = (data['parcels'] as List)
            .map(
              (p) => FarmParcel.fromJson(Map<String, dynamic>.from(p as Map)),
            )
            .toList();
        pendingSoil.addAll(
          (data['soilOutbox'] as List? ?? []).map(
            (item) => Map<String, dynamic>.from(item as Map),
          ),
        );
        pendingDeletes.addAll(
          Map<String, int>.from(data['deletions'] as Map? ?? {}),
        );
        setState(() {
          parcels
            ..clear()
            ..addAll(loaded);
        });
      }
      rememberParcels();
      if (!offline) await syncParcels();
    } catch (_) {
      if (mounted) {
        setState(
          () => syncError =
              'Copia locale non leggibile. I dati non sono stati sovrascritti.',
        );
      }
    }
  }

  Future<void> persistParcels() async {
    for (final parcel in parcels) {
      if (savedPayloads[parcel.id] != parcelPayload(parcel)) {
        parcel.pending = true;
      }
    }
    for (final id in savedPayloads.keys) {
      if (!parcels.any((p) => p.id == id) && (savedRevisions[id] ?? 0) > 0) {
        pendingDeletes[id] = savedRevisions[id]!;
      }
    }
    pendingSoil.removeWhere(
      (item) => !parcels.any((p) => p.id == item['parcel_id']),
    );
    rememberParcels();
    try {
      await writeCache();
    } catch (_) {
      if (mounted) {
        setState(
          () =>
              syncError = 'Salvataggio sul dispositivo non riuscito. Riprova.',
        );
      }
      return;
    }
    if (mounted) await syncParcels();
  }

  Future<void> syncParcels() async {
    if (!mounted || !ApiSession.instance.authenticated) return;
    if (syncing) {
      syncAgain = true;
      return;
    }
    setState(() {
      syncing = true;
      syncError = null;
    });
    try {
      do {
        syncAgain = false;
        await verifyWorkspaceGeneration();
        final response = await http
            .get(Uri.parse('$apiBaseUrl/parcels'))
            .timeout(const Duration(seconds: 20));
        if (!mounted) return;
        if (response.statusCode != 200) {
          throw Exception('Lettura server HTTP ${response.statusCode}');
        }
        final remote = (jsonDecode(response.body) as List)
            .map(
              (p) => FarmParcel.fromJson(Map<String, dynamic>.from(p as Map)),
            )
            .toList();
        for (final parcel in parcels) {
          if (pendingSoil.any((item) => item['parcel_id'] == parcel.id)) {
            parcel.pending = true;
          }
        }
        final pending = {
          for (final p in parcels.where((p) => p.pending)) p.id: p,
        };
        setState(() {
          parcels
            ..clear()
            ..addAll(
              remote.where(
                (p) =>
                    !pending.containsKey(p.id) &&
                    !pendingDeletes.containsKey(p.id),
              ),
            )
            ..addAll(pending.values);
          if (selectedId != null && !parcels.any((p) => p.id == selectedId)) {
            selectedId = null;
            clearSatelliteOverlay();
            clearWeather();
          }
        });
        rememberParcels();
        await writeCache();
        if (!mounted) return;
        for (final parcel in List<FarmParcel>.of(
          parcels.where((p) => p.pending),
        )) {
          if (!mounted) return;
          final sent = parcelPayload(parcel);
          final saved = await http
              .put(
                Uri.parse(
                  '$apiBaseUrl/parcels/${Uri.encodeComponent(parcel.id)}',
                ),
                headers: {'Content-Type': 'application/json'},
                body: jsonEncode(parcel.toJson()),
              )
              .timeout(const Duration(seconds: 20));
          if (!mounted) return;
          if (saved.statusCode == 409) {
            await resolveConflict(parcel, saved);
            continue;
          }
          if (saved.statusCode != 200) {
            throw Exception('Salvataggio HTTP ${saved.statusCode}');
          }
          final revision = (jsonDecode(saved.body)['revision'] as num).toInt();
          if (parcels.any((p) => identical(p, parcel))) {
            parcel.revision = revision;
            parcel.pending = parcelPayload(parcel) != sent;
            syncAgain = syncAgain || parcel.pending;
          } else {
            pendingDeletes[parcel.id] = revision;
            syncAgain = true;
          }
          rememberParcels();
          await writeCache();
        }
        for (final entry in Map<String, int>.of(pendingDeletes).entries) {
          if (!mounted) return;
          final response = await http
              .delete(
                Uri.parse(
                  '$apiBaseUrl/parcels/${Uri.encodeComponent(entry.key)}?revision=${entry.value}',
                ),
              )
              .timeout(const Duration(seconds: 20));
          if (!mounted) return;
          if (response.statusCode == 409) {
            final remoteParcel = remote
                .where((p) => p.id == entry.key)
                .firstOrNull;
            if (remoteParcel != null) {
              await resolveConflict(remoteParcel, response, deleting: true);
            }
            continue;
          }
          if (response.statusCode != 204 && response.statusCode != 404) {
            throw Exception('Eliminazione HTTP ${response.statusCode}');
          }
          pendingDeletes.remove(entry.key);
          await writeCache();
        }
        for (final item in List<Map<String, dynamic>>.of(pendingSoil)) {
          if (!mounted) return;
          final response = await http
              .post(
                Uri.parse('$apiBaseUrl/soil/analyses'),
                headers: {'Content-Type': 'application/json'},
                body: jsonEncode(item),
              )
              .timeout(const Duration(seconds: 20));
          if (!mounted) return;
          if (response.statusCode != 201) {
            throw Exception('Salvataggio analisi HTTP ${response.statusCode}');
          }
          pendingSoil.remove(item);
          soilRevision++;
          await writeCache();
        }
      } while (syncAgain && mounted);
      if (mounted) {
        setState(() {
          agronomyRevision++;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(
          () => syncError = 'Sincronizzazione non riuscita. Le modifiche restano sul dispositivo; premi Sincronizza per riprovare.',
        );
      }
    } finally {
      if (mounted) setState(() => syncing = false);
    }
  }

  Future<void> resolveConflict(
    FarmParcel parcel,
    http.Response response, {
    bool deleting = false,
  }) async {
    final detail = (jsonDecode(response.body) as Map)['detail'];
    if (detail is! Map) throw Exception('Conflitto da verificare sul server');
    final revision = (detail['revision'] as num).toInt();
    final deleted = detail['deleted'] == true;
    final keepLocal = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (context) => AlertDialog(
        title: const Text('Modifiche su un altro dispositivo'),
        content: Text(
          deleted
              ? '“${parcel.name}” è stata eliminata sul server. Puoi conservare una nuova copia delle modifiche locali.'
              : '“${parcel.name}” è stata modificata altrove. Scegli quale versione conservare.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Usa dati server'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: Text(
              deleting ? 'Conferma eliminazione' : 'Conserva modifiche locali',
            ),
          ),
        ],
      ),
    );
    if (!mounted) return;
    setState(() {
      if (keepLocal == true) {
        if (deleting) {
          pendingDeletes[parcel.id] = revision;
        } else if (deleted) {
          parcels.removeWhere((p) => p.id == parcel.id);
          final copy = FarmParcel(
            id: DateTime.now().microsecondsSinceEpoch.toString(),
            name: parcel.name,
            points: List.of(parcel.points),
            crop: parcel.crop,
            soil: Map.of(parcel.soil),
            pending: true,
          );
          parcels.add(copy);
          for (final item in pendingSoil.where(
            (item) => item['parcel_id'] == parcel.id,
          )) {
            item['parcel_id'] = copy.id;
          }
          if (selectedId == parcel.id) selectedId = copy.id;
        } else {
          parcel.revision = revision;
        }
        syncAgain = true;
      } else {
        parcels.removeWhere((p) => p.id == parcel.id);
        pendingDeletes.remove(parcel.id);
        pendingSoil.removeWhere((item) => item['parcel_id'] == parcel.id);
        if (!deleted && detail['current'] is Map) {
          parcels.add(
            FarmParcel.fromJson({
              ...Map<String, dynamic>.from(detail['current'] as Map),
              'revision': revision,
            }),
          );
        } else if (selectedId == parcel.id) {
          selectedId = null;
          clearSatelliteOverlay();
          clearWeather();
        }
      }
    });
    rememberParcels();
    await writeCache();
  }

  Future<void> importLegacyParcels() async {
    if (syncing) return;
    final prefs = await SharedPreferences.getInstance();
    final saved =
        prefs.getString('agroplan_parcels_v2_${ApiSession.instance.farmId}') ??
        prefs.getString('agroplan_parcels');
    if (!mounted) return;
    if (saved == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Nessuna copia precedente trovata su questo dispositivo.',
          ),
        ),
      );
      return;
    }
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Importa particelle precedenti'),
        content: Text(
          'Copiare le particelle di questo dispositivo nell’azienda ${ApiSession.instance.farmId}? La copia precedente sarà conservata.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Annulla'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Importa'),
          ),
        ],
      ),
    );
    if (!mounted || confirmed != true) return;
    try {
      final decoded = jsonDecode(saved);
      final rows = decoded is Map
          ? decoded['parcels'] as List
          : decoded as List;
      final imported = rows
          .map((p) => FarmParcel.fromJson(Map<String, dynamic>.from(p as Map)))
          .toList();
      setState(() {
        for (final parcel in imported) {
          if (!parcels.any((p) => p.id == parcel.id) &&
              !pendingDeletes.containsKey(parcel.id)) {
            parcel.revision = 0;
            parcel.pending = true;
            parcels.add(parcel);
          }
        }
      });
      await saveParcels();
    } catch (_) {
      if (mounted) {
        setState(
          () => syncError = 'La copia precedente non è leggibile. Il file originale è stato conservato.',
        );
      }
    }
  }
}
