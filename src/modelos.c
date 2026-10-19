#include "carac.h"
#include <ctype.h>
#include <stdio.h>
#include <string.h>

static const CtModelo modelos[] = {
#define RIGOL_MODEL(nome, serie, canais, mhz, tmin, tmax, vmin, validado) \
  {nome, serie, canais, mhz, tmin, tmax, vmin, validado},
#include "rigol_models.def"
#undef RIGOL_MODEL
};

const CtModelo *ct_modelo(const char *nome)
{
  if (!nome) return NULL;
  for (size_t k=0;k<sizeof modelos/sizeof modelos[0];++k)
    if (!strcmp(nome,modelos[k].nome)) return &modelos[k];
  return NULL;
}

void ct_listar_modelos(void)
{
  for (size_t k=0;k<sizeof modelos/sizeof modelos[0];++k)
    puts(modelos[k].nome);
}

static char *limpar(char *s)
{
  while (isspace((unsigned char)*s)) ++s;
  char *fim=s+strlen(s);
  while (fim>s && isspace((unsigned char)fim[-1])) *--fim='\0';
  for (char *p=s;*p;++p) *p=(char)toupper((unsigned char)*p);
  return s;
}

const CtModelo *ct_modelo_identidade(const char *id)
{
  char copia[256];
  if (strlen(id)>=sizeof copia) return NULL;
  strcpy(copia,id);
  char *campos[4], *inicio=copia;
  for (size_t k=0;k<4;++k) {
    char *virgula=strchr(inicio,',');
    if ((k<3 && !virgula) || (k==3 && virgula)) return NULL;
    if (virgula) *virgula='\0';
    campos[k]=limpar(inicio);
    if (!*campos[k]) return NULL;
    if (virgula) inicio=virgula+1;
  }
  if (strcmp(campos[0],"RIGOL") && strcmp(campos[0],"RIGOL TECHNOLOGIES")) return NULL;
  return ct_modelo(campos[1]);
}

int ct_validar_modelo(const CtConfig *cfg, const char *id, char *erro)
{
  const CtModelo *m=ct_modelo_identidade(id);
  if (!m) return ct_falha(erro,"Modelo Rigol sem perfil disponivel: %s",id);
  if (cfg->modelo && strcmp(cfg->modelo,"auto") && strcmp(cfg->modelo,m->nome))
    return ct_falha(erro,"Modelo selecionado %s; instrumento conectado %s. Nenhum ajuste enviado.",
                    cfg->modelo,m->nome);
  if ((!cfg->sinais && (cfg->ch_v>m->canais || cfg->ch_i>m->canais)) ||
      cfg->disparo_canal>m->canais)
    return ct_falha(erro,"Canal indisponivel no %s.",m->nome);
  for (unsigned k=0;k<cfg->n_canais;++k) {
    const CtCanal *ch=&cfg->canais[k];
    if(ch->numero>m->canais) return ct_falha(erro,"Canal indisponivel no %s.",m->nome);
    if(cfg->configurar && (ch->escala<m->escala_min*ch->sonda || ch->escala>10*ch->sonda))
      return ct_falha(erro,"Escala vertical fora da faixa do %s.",m->nome);
  }
  if (!cfg->configurar) return 0;
  if (cfg->tempo_div<m->tempo_min || cfg->tempo_div>m->tempo_max)
    return ct_falha(erro,"Tempo por divisao fora da faixa do %s: %.9g a %.9g s.",
                    m->nome,m->tempo_min,m->tempo_max);
  if (!cfg->n_canais && (cfg->escala_v<m->escala_min*cfg->sonda_v || cfg->escala_v>10*cfg->sonda_v ||
      cfg->escala_shunt<m->escala_min*cfg->sonda_i || cfg->escala_shunt>10*cfg->sonda_i))
    return ct_falha(erro,"Escala vertical fora da faixa do %s para a ponta selecionada.",m->nome);
  return 0;
}
