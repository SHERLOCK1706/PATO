# PATO no servidor (equipe, com login)

**Servidor recomendado:** 2 vCPU, 4 GB de RAM, 40 GB de disco, Linux (Ubuntu 24.04). Custo aproximado: R$ 40 a R$ 130/mês
(VPS) + domínio .com.br (~R$ 40/ano). O https (cadeado) é gratuito (Let's Encrypt, pelo Caddy).

## Instalação (uma vez)
1. No servidor: instale o Docker (`curl -fsSL https://get.docker.com | sh`).
2. Copie a pasta do PATO para o servidor (ou `git clone` do repositório).
3. Aponte o domínio (registro A) para o IP do servidor e edite `DOMINIO` em `servidor/docker-compose.yml`.
4. `cd servidor && docker compose up -d --build`
5. Abra `https://seu-dominio`: no primeiro acesso, crie o **administrador**. Depois, em 👤 → Usuários, crie as demais pessoas
   (login e senha provisória — cada um define a sua senha no primeiro acesso).

## Perfis
- **Administrador**: cria/desativa usuários, define senha provisória, e tudo dos editores.
- **Editor**: monta e altera os PATOs, salva versões, copia projetos como modelo.
- **Leitor**: consulta e baixa (planilhas, memória de cálculo); não altera.
Todos veem todos os projetos. O histórico de cada projeto mostra quem fez cada alteração.

## Segurança
- Senhas guardadas com scrypt (não reversível); 5 tentativas erradas bloqueiam o login por 5 minutos.
- Sessão expira após 8 horas sem uso; desativar um usuário derruba a sessão dele na hora.
- Use sempre https (o Caddy já faz). Não exponha a porta 8000 diretamente.

## Backup
Tudo fica em `servidor/dados` (banco, versões dos projetos, anexos). Agende o `backup.sh` (cron, todo dia às 3h) e copie a
pasta `backups` para fora do servidor de vez em quando. Cada projeto também pode ser baixado como `.pato` pela tela.

## Atualizar o sistema
`git pull` (ou copie a nova versão) e `docker compose up -d --build`. Os dados ficam no volume e não são apagados.

## Sem servidor: só na rede do escritório
No computador que fica ligado: `python -m pato_app --host 0.0.0.0 --login` e os demais acessam `http://IP-DO-COMPUTADOR:8000`.
