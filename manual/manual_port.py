# -*- coding: utf-8 -*-
"""Manual em português (Manual_PORT.pdf). Mesma estrutura do conteúdo em espanhol de hacer_manual.py; nomes de botões como na interface em português (tratamento: você)."""
C = "<font name='Courier'>%s</font>"
TEXTOS = dict(titulo="Gerenciador de música", subtitulo="Manual de uso", version="Versão {v} - para Windows 10, Windows 11 e Mac",
              lema="A sua música, organizada, no seu próprio computador.<br/>Sem contas, sem internet, sem instalar Python.",
              pie="Gerenciador de música - Manual", pagina="Página {n}")

CONTENIDO = [
    ("h1", "1. O que é"),
    ("p", "O <b>Gerenciador de música</b> é um programa para organizar a sua própria música no seu computador: músicas, letras, versões, masters, stems, capas e vídeos. "
          "Você a escuta no navegador, marca rascunhos, une duplicatas, prepara álbuns e mixtapes em MP3 com suas letras, e pode normalizar o volume delas."),
    ("p", "Tudo acontece <b>no seu computador</b>: o programa só atende a sua própria máquina (endereço 127.0.0.1), não tem contas, não envia estatísticas e a sua música "
          "não é copiada para lugar nenhum; ela é lida da sua pasta. <b>Você não precisa instalar o Python</b> nem mais nada."),
    ("p", "A pasta que você recebe contém só isto: o executável (" + C % "GestorMusica.exe" + " no Windows, " + C % "GestorMusica.app" + " no Mac), "
          "uma pasta de suporte (" + C % "_internal" + " no Windows; não mexa nela), uma pasta " + C % "datos" + " vazia e este manual."),

    ("h1", "2. Instalação e primeira execução"),
    ("h2", "Windows 10 e Windows 11"),
    ("li", ["Descompacte o zip numa pasta sua, por exemplo <i>Documentos\\GestorMusica</i>. Não o execute de dentro do zip e evite pastas protegidas como <i>Arquivos de Programas</i>.",
            "Dê um duplo clique em <b>GestorMusica.exe</b>. Abre-se uma pequena janela de texto (é o motor do programa: <b>feche-a para sair</b>) e, após alguns segundos, o seu navegador abre com o gerenciador.",
            "<b>Aviso do Windows (SmartScreen):</b> como o programa não é assinado, pode aparecer «O Windows protegeu o computador». Clique em <b>Mais informações</b> e depois em <b>Executar assim mesmo</b>.",
            "Se o zip vier da internet, antes de descompactar você pode clicar com o botão direito no zip, escolher <i>Propriedades</i> e marcar <b>Desbloquear</b>.",
            "Se o antivírus o bloquear por engano (às vezes acontece com programas sem assinatura), adicione a pasta como exceção.",
            "O firewall do Windows pode perguntar se você permite o acesso: o programa só usa o seu próprio computador; você pode cancelar e funciona igual."]),
    ("h2", "Mac (Intel e Apple Silicon)"),
    ("li", ["Há duas versões: <b>apple-silicon</b> (Macs M1, M2, M3, M4…) e <b>intel</b>. Se você não sabe qual tem: menu Apple > <i>Sobre este Mac</i>; se disser Apple M…, use apple-silicon.",
            "Descompacte o zip (duplo clique) e mova a pasta para, por exemplo, <i>Documentos</i>. Os seus dados são salvos <b>junto ao .app</b>, então não o deixe dentro de Aplicativos "
            "(se não for possível gravar ali, usa-se <i>~/Library/Application Support/GestorMusica</i>).",
            "<b>Aviso do Gatekeeper:</b> o aplicativo não é assinado pela Apple. Na primeira vez, clique com o <b>botão direito (ou Control+clique) em GestorMusica.app > Abrir > Abrir</b>. "
            "Só é preciso uma vez. Se o macOS disser que está «danificado», abra o Terminal e digite (troque o caminho pelo seu):"]),
    ("cod", "xattr -dr com.apple.quarantine /caminho/para/GestorMusica.app"),
    ("li", ["Ao abrir você não verá uma janela própria: o navegador abre com o gerenciador. Para sair, botão direito no ícone do Dock > <i>Sair</i>."]),
    ("h2", "A primeira vez"),
    ("p", "Aparece uma caixa para <b>escolher a pasta da sua biblioteca</b> de música (pode ser uma pasta nova e vazia). No Windows o programa também pergunta o seu nome artístico e o titular do copyright (para os mixtapes); "
          "no Mac você pode colocá-los depois em <b>Configurações</b>. Tudo é salvo em " + C % "config.json" + ", junto ao executável. Depois o navegador abre em " + C % "http://127.0.0.1:8765/" +
          ". Se essa porta estiver ocupada, tentam-se as seguintes e a janela de texto mostra o endereço correto."),

    ("h1", "3. A biblioteca e a sua estrutura"),
    ("p", "O gerenciador entende esta estrutura e a cria sozinho dentro da sua pasta:"),
    ("cod", "sua-biblioteca/\n  unreleased/            músicas sem publicar\n     Minha musica/\n     Meu projeto/        pasta com várias músicas = projeto ou álbum em preparação\n"
            "        01 Musica A/\n  prereleased/           prévias\n  published/\n     Singles/Meu single/\n     Albumes/Meu album/01 Musica A/\n"
            "  ARTE/                  capas, imagens e vídeos\n  MIXTAPES/              mixtapes gerados"),
    ("p", "Dentro de cada pasta de música:"),
    ("cod", "letra.txt      a letra (a primeira linha pode ser o título)\náudio solto    .wav .mp3 .m4a .flac .aif\nversiones/     versões e mixes\nmaster/        o master\n"
           "stems/         faixas separadas\nsesiones/ docs/ midi/ otros/"),
    ("li", ["As pastas cujo nome começa por <b>_</b> ou <b>.</b> são ignoradas.",
            "O título vem do nome da pasta (um número inicial como «01 » é retirado).",
            "Não é preciso criá-lo à mão: use <b>+ Adicionar músicas</b> ou a seção <b>Importar</b> e o gerenciador classifica cada arquivo.",
            "Se você mover uma pasta à mão, aperte <b>Atualizar</b>: a música é reconhecida pela letra e pelo áudio e mantém suas estrelas, notas e marcas.",
            "O seu trabalho no gerenciador (estrelas, notas, nomes, rascunhos…) fica na pasta <b>datos</b>, junto ao executável; <b>não</b> dentro da sua biblioteca."]),

    ("h1", "4. As seções"),
    ("h2", "Álbuns"),
    ("p", "Álbuns, singles, prévias e projetos, com o seu progresso. <b>+ Novo álbum</b> cria um: adicione músicas arrastando-as da lista da esquerda, ordene-as arrastando umas entre as outras "
          "e remova-as com o X (a música não é apagada nem movida da sua pasta). «Mudar capa» envia uma imagem ou escolhe outra já existente; «Recortar» prepara 1:1, 4:3, 3:4, 16:9 e 9:16 sem tocar no original."),
    ("h2", "Músicas"),
    ("p", "Todas as músicas, com busca e filtros (aperte um filtro de novo para tirá-lo, ou <b>Limpar filtros</b>). Em cada uma: reproduzir versões, estrelas, notas, renomear "
          "(só muda o nome no gerenciador, não as suas pastas) e <b>unificar duplicatas</b> (selecione várias com Ctrl/Shift, botão direito > Unificar). "
          "Teclado: setas para cima/baixo trocam de música; a barra de espaço reproduz ou pausa."),
    ("h2", "Letras"),
    ("p", "Leia e busque dentro das letras, também por temática."),
    ("h2", "Rascunhos"),
    ("p", "Marque letras que não são para compartilhar (arraste-as para o botão <i>Rascunhos</i>). Elas não entram nos mixtapes."),
    ("h2", "Mixtape"),
    ("p", "Precisa do <b>ffmpeg</b> (seção 5). Crie quantos mixtapes quiser com nome, qualidade (128, 192 ou 320 kbps) e aviso de copyright. Arraste músicas para o mixtape ou use «Adicionar a um mixtape…»: "
          "cria-se a sua versão MP3 em <i>MIXTAPES/_versiones</i> (a sua música original não é tocada). Leva capa de fita cassete com o título e o © com o seu nome e ano. "
          "<b>Enviar</b> cria um ZIP com este conteúdo: um arquivo HTML (<i>Abrir.html</i>) que o destinatário abre com duplo clique, sem instalar nada e sem internet, mostrando a capa, a lista de faixas, um player e a letra da faixa que está tocando; a pasta <i>Musicas</i> com os MP3 (<i>NN - Título.mp3</i>); a pasta <i>Letras</i> com um .txt por música; <i>COPYRIGHT.txt</i> e <i>Capa.jpg</i>. A letra também vai dentro da etiqueta de cada MP3 (letra não sincronizada). Os nomes do HTML e das pastas seguem o idioma escolhido em Ajustes. A caixa <b>Tudo em um único HTML</b> coloca o áudio dentro do próprio HTML (um único arquivo), só para mixtapes pequenos: acima de cerca de 25 MB o gerenciador avisa e recomenda o ZIP normal."),
    ("h2", "Pendentes"),
    ("p", "O que falta por música ou álbum: sem letra, sem master, sem capa etc."),
    ("h2", "Arte e vídeo"),
    ("p", "Capas, imagens e clipes de cada música ou álbum. As miniaturas são salvas em <i>datos/thumbs</i>."),
    ("h2", "Estado (dentro de Início)"),
    ("p", "Embaixo das informações do Início você verá «Estado da sua música»: o progresso da sua música: letra, versão, stems, master, capa e publicada; o que falta; e, se você os importar de um CSV, relatórios de plataformas (por mês, plataforma, país, música). "
          "Os relatórios são lidos no seu computador. «Conexões» inclui um conector opcional do Spotify que só consulta o catálogo público se você o ativar."),
    ("h2", "Importar (dentro de Configurações)"),
    ("p", "Abre-se em Configurações (a engrenagem ⚙), em «Minha música», com «Importar música de outras pastas…». É um assistente de 4 passos (Escolher pasta > Procurar > Revisar > Copiar) para organizar rascunhos, versões, stems, gravações ao vivo e projetos do seu DAW a partir de qualquer pasta. "
          "Ele <b>copia</b> para <i>unreleased/&lt;Título&gt;</i>; nunca move nem apaga a origem nem sobrescreve (acrescenta « (2)»). Detecta duplicatas e agrupa por título parecido. "
          "Cada cópia fica num diário e pode ser desfeita."),
    ("h2", "Configurações (a engrenagem ⚙ junto a «Minha música»)"),
    ("p", "No alto, à esquerda, junto a «Minha música». Aqui você muda a pasta da biblioteca (tudo é lido de novo na hora), o seu nome artístico, o titular do copyright e o <b>Idioma</b> da interface. Aqui você também encontra a importação de música."),
    ("h2", "Masterização"),
    ("p", "Há três lugares: a aba <b>Masterização</b> de cada álbum, o botão <b>Masterizar</b> na ficha de cada música e o botão <b>Masterizar</b> na página de cada mixtape."),
    ("p", "Em cada álbum, a aba <b>Masterização</b> mede o volume (LUFS), iguala as músicas (cada uma, ou relativo ao álbum), aplica limitador de picos, cortes, fades e silêncios, "
          "escreve etiquetas (ID3), adiciona a capa e exporta um ZIP, ou salva os masters na biblioteca (<i>master/NN - Título (máster).wav</i>; nunca sobrescreve e pede confirmação). "
          "O cálculo é feito no seu navegador."),
    ("p", "Num mixtape, os masters são salvos em <i>MIXTAPES/_masters</i> (nunca nas pastas das suas músicas) e você pode usá-los nesse mixtape ou voltar às versões originais. "
          "O resultado pode ser salvo como versão nova, sem sobrescrever nada."),

    ("h1", "5. Programa opcional: ffmpeg"),
    ("p", "Não vai dentro do programa por causa de sua licença. Sem ele tudo funciona, exceto os mixtapes MP3."),
    ("h2", "ffmpeg (mixtapes)"),
    ("li", ["<b>Windows:</b> no PowerShell digite " + C % "winget install Gyan.FFmpeg" + ", ou baixe o ffmpeg de ffmpeg.org e deixe o <b>ffmpeg.exe junto ao GestorMusica.exe</b>.",
            "<b>Mac:</b> instale o Homebrew (brew.sh) e digite " + C % "brew install ffmpeg" + "; ou deixe o arquivo <b>ffmpeg</b> na pasta junto ao GestorMusica.app.",
            "Reinicie o gerenciador depois de instalá-lo."]),

    ("h1", "6. Backups e desfazer"),
    ("li", ["Faça backup de <b>duas coisas</b>: a sua pasta de biblioteca, e a pasta <b>datos</b> junto com o <i>config.json</i> (estão junto ao executável).",
            "Para passar o programa a outro computador: copie a pasta do programa com <i>datos</i> e <i>config.json</i>, e em Configurações aponte para a biblioteca nova.",
            "O gerenciador <b>nunca apaga</b> os seus arquivos. Quando move algo (unificar, mover uma versão, importar) anota em <i>datos/diario_movimientos.jsonl</i>, e isso pode ser desfeito. "
            "A seção Importar tem o seu próprio desfazer. Para o diário geral, abra um terminal na pasta do programa e digite:"]),
    ("cod", "Windows:  GestorMusica.exe --run-script deshacer.py            (só simula)\n          GestorMusica.exe --run-script deshacer.py --apply    (desfaz)\n"
            "Mac:      GestorMusica.app/Contents/MacOS/GestorMusica --run-script deshacer.py --apply"),
    ("li", ["Ao atualizar para uma versão nova, substitua a pasta do executável, mas conserve <i>datos</i> e <i>config.json</i>."]),

    ("h1", "7. Privacidade e segurança"),
    ("li", ["O servidor só atende o seu próprio computador (127.0.0.1) e rejeita pedidos que não venham da sua própria página.",
            "Não há contas, estatísticas nem telemetria. A sua música, letras e dados não saem do seu computador.",
            "A única coisa que pode usar a internet, e só se você pedir: o conector opcional do Spotify (catálogo público).",
            "O token de <i>datos/agente.json</i> serve só para parear uma página web publicada com o seu programa; se você não a usa, ignore-o e não o compartilhe."]),

    ("h1", "8. Solução de problemas"),
    ("tabla", [["Problema", "O que fazer"],
               ["O Windows diz «protegeu o computador»", "Mais informações > Executar assim mesmo (seção 2)."],
               ["Mac: «não pode ser aberto» ou «danificado»", "Botão direito > Abrir; se persistir, o comando xattr da seção 2."],
               ["O navegador não abre", "Abra à mão o endereço da janela de texto (normalmente http://127.0.0.1:8765/)."],
               ["«Porta ocupada»", "O gerenciador tenta as portas seguintes; use o endereço que ele mostra. Feche cópias antigas."],
               ["Biblioteca vazia ou desatualizada", "Aperte Atualizar; verifique a pasta em Configurações."],
               ["Uma música não aparece", "Verifique se a sua pasta não começa por _ ou . e se tem áudio ou letra."],
               ["Mixtapes: «Não encontro o ffmpeg»", "Instale o ffmpeg (seção 5) e reinicie o gerenciador."],
               ["Mac: não salva dados ou pede permissões", "Mova a pasta para Documentos (não para Aplicativos) e conceda acesso a pastas se o macOS pedir."],
               ["Algo estranho depois de atualizar", "Feche o programa, apague datos/thumbs e abra-o de novo (é regenerado). Não apague o resto de datos."],
               ["Quero começar do zero", "Feche o programa e renomeie a pasta datos; a sua música não é tocada."]]),
]
