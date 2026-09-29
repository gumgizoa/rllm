docker run -d --name rllm-train --gpus all --network host --shm-size 32g \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /vast-ib/MMI/home/kyuminkim:/vast-ib/MMI/home/kyuminkim \
  -v /data/MMI/kyuminkim:/data/MMI/kyuminkim \
  pytorch/pytorch:2.12.1-cuda13.0-cudnn9-devel sleep infinity
docker exec -it rllm-train bash