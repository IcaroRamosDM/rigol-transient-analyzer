"""Workflow extensions; instrument operations share the acquisition lock."""
from contextlib import contextmanager
from .common import ACTIVE, DEFAULTS, Problem, settings
from .diagnostics import diagnose


class Workbench:
    @contextmanager
    def instrument_operation(self, data):
        cfg=settings(data.get("settings",{}),self.connection.get("model"))
        with self.lock:
            if self.closed or self.scope["busy"] or self.connection.get("checking") or (self.job and self.job["state"] in ACTIVE):
                raise Problem("Aguarde a operação em andamento.",409)
            if not (self.connection.get("connected") and (self.connection["ip"],self.connection["port"])==(cfg["ip"],cfg["port"]) and cfg["model"] in {"auto",self.connection["model"]}):
                raise Problem("Conecte o Rigol neste endereço antes de configurar.",409)
            cfg=settings(cfg|{"model":self.connection["model"]})
            self.scope.update(busy=True,error="")
        try:
            yield cfg
        except OSError as error:
            raise Problem("Não foi possível comunicar com o Rigol. Verifique o cabo e tente conectar novamente.",502) from error
        finally:
            with self.lock:
                self.scope["busy"]=False

    def save_profile(self,data):
        values=data.get("settings",{})
        with self.lock:
            connected=self.connection
            matched=connected.get("connected") and isinstance(values,dict) and (
                values.get("ip", DEFAULTS["ip"]),values.get("port",DEFAULTS["port"]))==(
                connected.get("ip"),connected.get("port"))
            detected=connected.get("model") if matched else None
        cfg=settings(values,detected)
        if cfg["model"]=="auto" and detected:
            cfg["model"]=detected
        return self.profiles.save(data|dict(settings=cfg))

    def diagnose(self,data):
        with self.instrument_operation(data) as cfg:
            result=diagnose(cfg)
            with self.lock:
                self.scope["snapshot"]=result["state"]
            return result

    def backup(self,data):
        with self.instrument_operation(data) as cfg:
            return self.backups.create(cfg)

    def restore(self,data):
        with self.instrument_operation(data) as cfg:
            result=self.backups.restore(data.get("id"),cfg)
            with self.lock:
                self.scope["snapshot"]=result["snapshot"]
            return result

    def compare(self,data):
        from .comparison import compare
        return compare(self.store,data)

    def report(self,data):
        from .reports import report
        return report(self.store,data)
